# Исправления логики удаления файлов

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-12-26

## Проблемы

### 1. `hard_delete_file` не удаляет все версии файла

**Текущее поведение**: `hard_delete_file(file_id)` удаляет только одну запись по `file_id`.

**Требуемое поведение**: При hard delete должны удаляться **ВСЕ версии файла** (все записи с одинаковым `path` или `original_path`) и все физические копии в версиях.

### 2. `fix_deleted_files` должна использовать `unmark_file_deleted`

**Текущее поведение**: `fix_deleted_files` только обновляет БД, не перемещает файлы из версий обратно.

**Требуемое поведение**: Если файл существует в проекте, но помечен как deleted, нужно использовать `unmark_file_deleted` для правильного восстановления (перемещения файла из версий обратно).

## Исправления

### Исправление 1: `hard_delete_file` - удаление всех версий

```python
def hard_delete_file(self, file_id: int) -> None:
    """
    Permanently delete file and all related data (hard delete).
    
    Deletes ALL versions of the file (all records with same path or original_path)
    and ALL physical copies in version directories.
    
    This is final deletion - removes:
    - ALL physical files from version_dir (if exists)
    - ALL file records with same path/original_path
    - All chunks (and removes from FAISS)
    - All classes, functions, methods
    - All AST trees
    - All vector indexes
    
    Use with caution - cannot be recovered.
    
    Args:
        file_id: File ID to delete (will delete ALL versions of this file)
    """
    from pathlib import Path
    
    # Get file info before deletion
    with self._lock:
        assert self.conn is not None
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT path, original_path, version_dir, project_id FROM files WHERE id = ?", 
            (file_id,)
        )
        row = cursor.fetchone()
        if not row:
            logger.warning(f"File ID {file_id} not found")
            return
        
        file_path = row[0]
        original_path = row[1]
        version_dir = row[2] if len(row) > 2 else None
        project_id = row[3] if len(row) > 3 else None
        
        # Find ALL versions of this file (by path or original_path)
        if original_path:
            # Find by original_path (all versions that were moved from same location)
            cursor.execute(
                """
                SELECT id, path, version_dir 
                FROM files 
                WHERE project_id = ? AND original_path = ?
                """,
                (project_id, original_path)
            )
        else:
            # Find by current path
            cursor.execute(
                """
                SELECT id, path, version_dir 
                FROM files 
                WHERE project_id = ? AND path = ?
                """,
                (project_id, file_path)
            )
        
        all_versions = cursor.fetchall()
        
        # Delete ALL physical files in version directories
        deleted_files = set()
        for version_row in all_versions:
            version_file_path = version_row[1]
            version_file_dir = version_row[2] if len(version_row) > 2 else None
            
            if version_file_path and version_file_dir:
                try:
                    file_path_obj = Path(version_file_path)
                    if file_path_obj.exists() and str(file_path_obj) not in deleted_files:
                        file_path_obj.unlink()
                        deleted_files.add(str(file_path_obj))
                        logger.info(f"Deleted physical file: {version_file_path}")
                        # Try to remove empty parent directories
                        try:
                            parent = file_path_obj.parent
                            if parent.exists() and not any(parent.iterdir()):
                                parent.rmdir()
                        except Exception:
                            pass  # Ignore errors removing directories
                except Exception as e:
                    logger.warning(f"Failed to delete physical file {version_file_path}: {e}")
        
        # Delete ALL versions from database
        for version_row in all_versions:
            version_id = version_row[0]
            # Clear all data for this version
            self.clear_file_data(version_id)
            # Delete the file record
            cursor.execute("DELETE FROM files WHERE id = ?", (version_id,))
        
        self.conn.commit()
        logger.info(f"Hard deleted {len(all_versions)} version(s) of file ID {file_id}")
```

### Исправление 2: `fix_deleted_files` - использование `unmark_file_deleted`

```python
# В методе execute класса FixDeletedFilesCommand, заменить:
# Текущий код (строки 530-559):
restored_count = 0
with self.database._lock:
    cursor = self.database.conn.cursor()
    for file_to_restore in result["to_restore"]:
        try:
            restore_path = file_to_restore["restore_path"]
            file_id = file_to_restore["id"]
            
            # Update database - set deleted=0, clear original_path and version_dir
            cursor.execute(
                """
                UPDATE files 
                SET deleted = 0, 
                    original_path = NULL, 
                    version_dir = NULL, 
                    path = ?,
                    updated_at = julianday('now')
                WHERE id = ?
                """,
                (restore_path, file_id),
            )
            restored_count += 1
            logger.info(f"Restored file ID {file_id}: {restore_path}")
        except Exception as e:
            logger.error(f"Error restoring file ID {file_to_restore['id']}: {e}")

# На:
restored_count = 0
for file_to_restore in result["to_restore"]:
    try:
        # Use unmark_file_deleted to properly restore file (moves from versions back)
        # Try by original_path first, then by current path
        restore_path = file_to_restore["restore_path"]
        original_path = file_to_restore.get("original_path")
        current_path = file_to_restore.get("current_path")
        
        # Try to restore using unmark_file_deleted
        # This will move file from version_dir back to original_path
        if original_path:
            success = self.database.unmark_file_deleted(original_path, self.project_id)
        elif current_path:
            success = self.database.unmark_file_deleted(current_path, self.project_id)
        else:
            logger.warning(f"Cannot restore file ID {file_to_restore['id']}: no path")
            continue
        
        if success:
            restored_count += 1
            logger.info(f"Restored file: {restore_path}")
        else:
            # If unmark failed (file not in versions), just update DB status
            # This handles case where file exists but wasn't moved to versions
            file_id = file_to_restore["id"]
            with self.database._lock:
                cursor = self.database.conn.cursor()
                cursor.execute(
                    """
                    UPDATE files 
                    SET deleted = 0, 
                        original_path = NULL, 
                        version_dir = NULL, 
                        path = ?,
                        updated_at = julianday('now')
                    WHERE id = ?
                    """,
                    (restore_path, file_id),
                )
                self.database.conn.commit()
            restored_count += 1
            logger.info(f"Restored file ID {file_id} (DB only): {restore_path}")
    except Exception as e:
        logger.error(f"Error restoring file ID {file_to_restore['id']}: {e}")
```

## Проверка

### 1. `mark_file_deleted` - перемещение (не копирование)

✅ **Проверено**: Использует `shutil.move()` (строка 421 в files.py) - правильно перемещает файл.

### 2. `hard_delete_file` - удаление всех версий

❌ **Требует исправления**: Сейчас удаляет только одну запись. Нужно удалять все версии.

### 3. `fix_deleted_files` - не создает файлы

✅ **Проверено**: Только обновляет БД, не создает файлы. Но нужно использовать `unmark_file_deleted` для правильного восстановления.

### 4. Полная очистка на test_data

📝 **Требует тестирования**: Создан скрипт `scripts/test_file_deletion_logic.py` для проверки.

## Тестирование

Запустить тесты:
```bash
cd /home/vasilyvz/projects/tools/code_analysis
python scripts/test_file_deletion_logic.py
```

