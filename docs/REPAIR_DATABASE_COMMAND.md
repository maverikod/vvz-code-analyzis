# Команда repair_database

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-12-26

## Описание

Команда `repair_database` восстанавливает целостность базы данных на основе реального наличия файлов в файловой системе.

## Логика работы

### 1. Файл есть в каталоге проекта
- **Действие**: Снимается пометка `deleted`
- **Обновление БД**: `deleted = 0`, `original_path = NULL`, `version_dir = NULL`

### 2. Файл есть в версиях, но нет в проекте
- **Действие**: Устанавливается метка `deleted`
- **Обновление БД**: Вызывается `mark_file_deleted()` для перемещения файла в версии и установки флага

### 3. Файл отсутствует везде
- **Действие**: Восстановление из CST узлов (TODO: требует реализации)
- **Процесс**:
  - Файл восстанавливается из AST дерева
  - Помещается в версии
  - Добавляется в файлы проекта, если нет пометки на удаление

## Использование

### Через MCP

```python
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="repair_database",
    params={
        "root_dir": "/path/to/project",
        "version_dir": "data/versions",  # optional
        "dry_run": False  # optional
    }
)
```

### Параметры

- `root_dir` (required): Корневой каталог проекта
- `project_id` (optional): UUID проекта (если не указан, определяется автоматически)
- `version_dir` (optional): Каталог для версий удаленных файлов (по умолчанию: `data/versions`)
- `dry_run` (optional): Если `True`, только показывает что будет исправлено, не вносит изменения

## Результат

Возвращает словарь с статистикой:

```python
{
    "files_in_project_restored": [...],      # Файлы восстановленные в проекте
    "files_in_versions_marked_deleted": [...],  # Файлы помеченные как deleted
    "files_restored_from_cst": [...],        # Файлы восстановленные из CST
    "errors": [...],                         # Ошибки
    "message": "...",                        # Сводное сообщение
    "dry_run": false
}
```

## Текущий статус

✅ **Реализовано**:
- Проверка файлов в проекте и версиях
- Восстановление файлов из проекта (снятие пометки deleted)
- Помечение файлов в версиях как deleted

⚠️ **Требует доработки**:
- Восстановление файлов из CST узлов (AST дерева)
- Полное восстановление структуры файла из AST

## Тестирование

Скрипт для тестирования: `scripts/test_repair_database.py`

```bash
cd /home/vasilyvz/projects/tools/code_analysis
python scripts/test_repair_database.py
```

## Файлы

- **Команда**: `code_analysis/commands/file_management.py` - `RepairDatabaseCommand`
- **MCP обертка**: `code_analysis/commands/file_management_mcp_commands.py` - `RepairDatabaseMCPCommand`

