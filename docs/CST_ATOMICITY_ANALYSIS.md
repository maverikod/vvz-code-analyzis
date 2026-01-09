# Анализ атомарности операций с CST узлами

**Автор**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Дата**: 2026-01-09

## Executive Summary

Проведен анализ текущей реализации операций с CST узлами в команде `compose_cst_module`. Обнаружены критические проблемы с атомарностью и валидацией:

1. ❌ **Нет атомарности**: Запись в базу данных происходит после записи файла, что может привести к рассинхронизации
2. ❌ **Нет валидации линтером**: Проверяется только компиляция и docstrings, но нет проверки линтером (flake8, mypy)
3. ❌ **Нет временного файла**: Код записывается сразу в целевой файл, а не во временный
4. ❌ **Нет транзакций**: Операции с базой данных не используют транзакции для атомарности
5. ❌ **Нет отката**: При ошибке после записи файла нет механизма отката изменений
6. ❌ **Нет проверки всего файла**: Проверяется только измененный код, а не весь файл целиком
7. ❌ **Нет атомарного перемещения**: Временный файл не перемещается атомарно на место исходного

## Ключевые требования

1. **Компиляция всего файла**: После формирования CST узлов нужно компиллировать ВЕСЬ файл, а не только измененные части
2. **Проверка всего файла**: Линтер, type checker и другие инструменты должны проверять ВЕСЬ файл
3. **Атомарное перемещение**: После записи в базу временный файл должен быть атомарно перемещен на место исходного

## 1. Текущая реализация

### 1.1 Процесс в `compose_cst_module`

Текущий процесс (файл `code_analysis/commands/cst_compose_module_command.py`):

```python
# 1. Формирование CST узлов (строки 333-365)
current_source = old_source
if replace_ops:
    current_source, replace_stats = apply_replace_ops(current_source, replace_ops)
if insert_ops:
    current_source, insert_stats = apply_insert_ops(current_source, insert_ops)
if create_ops:
    current_source, create_stats = apply_create_ops(current_source, create_ops)

# 2. Проверка компиляции (строка 367)
ok, compile_error = compile_module(new_source, filename=str(target))
if not ok:
    return ErrorResult(...)  # ❌ Файл еще не записан - OK

# 3. Проверка docstrings (строка 387)
docstring_valid, docstring_error, docstring_errors = validate_module_docstrings(new_source)
if not docstring_valid:
    return ErrorResult(...)  # ❌ Файл еще не записан - OK

# 4. Запись файла (строка 436)
if apply:
    backup_path = write_with_backup(target, new_source, create_backup=create_backup)
    # ❌ ПРОБЛЕМА: Файл уже записан на диск!

# 5. Обновление базы данных (строка 463)
update_result = database.update_file_data(
    file_path=rel_path,
    project_id=project_id,
    root_dir=root_path,
)
# ❌ ПРОБЛЕМА: Если здесь ошибка, файл уже изменен, но база не обновлена!
```

### 1.2 Проблемы текущей реализации

#### Проблема 1: Нет атомарности записи в базу

**Текущий процесс:**
1. Файл записывается на диск (строка 436)
2. Затем обновляется база данных (строка 463)

**Проблема:** Если ошибка происходит между шагами 1 и 2, файл уже изменен, но база данных не обновлена. Это приводит к рассинхронизации.

**Пример сценария:**
```python
# Файл записан
write_with_backup(target, new_source, create_backup=create_backup)

# Ошибка при обновлении базы
database.update_file_data(...)  # ❌ Exception: Database connection lost
# Результат: Файл изменен, но база данных содержит старые данные
```

#### Проблема 2: Нет валидации линтером

**Текущая валидация:**
- ✅ Компиляция (`compile_module`)
- ✅ Docstrings (`validate_module_docstrings`)
- ❌ Линтер (flake8) - отсутствует
- ❌ Type checker (mypy) - отсутствует
- ❌ Другие инструменты проверки - отсутствуют

**Проблема:** Код может быть синтаксически корректным, но содержать ошибки стиля, типов и другие проблемы, которые обнаружатся только после записи в базу.

#### Проблема 3: Нет временного файла

**Текущий процесс:**
- Код формируется в памяти
- Проверяется компиляция и docstrings
- Записывается сразу в целевой файл

**Проблема:** Если валидация линтером требует файл на диске, текущий подход не позволяет проверить код перед записью.

#### Проблема 4: Нет транзакций

**Текущая реализация `update_file_data`:**
```python
# Очистка старых данных
self.clear_file_data(file_id)  # ❌ Нет транзакции

# Сохранение AST
database.save_ast_tree(...)  # ❌ Нет транзакции

# Сохранение CST
database.save_cst_tree(...)  # ❌ Нет транзакции

# Сохранение entities
database.add_class(...)  # ❌ Нет транзакции
```

**Проблема:** Если ошибка происходит в середине процесса, часть данных может быть сохранена, а часть - нет. Это приводит к несогласованному состоянию базы данных.

#### Проблема 5: Нет отката

**Текущий процесс:**
- Файл записывается на диск
- Если ошибка при обновлении базы, файл остается измененным
- Нет механизма отката изменений файла

**Проблема:** При ошибке после записи файла нет способа вернуть файл к исходному состоянию.

## 2. Требования к исправлению

### 2.1 Атомарность

**Требование:** Добавление/изменение узлов CST в базу должно быть атомарным с синхронизацией AST узлов.

**Решение:**
1. Использовать транзакции базы данных для всех операций записи
2. Записывать CST и AST узлы в одной транзакции
3. Откатывать транзакцию при любой ошибке

### 2.2 Процесс валидации

**Требование:** Сначала формируем узлы CST, потом переводим их в код во временном файле, проверяем ВЕСЬ файл линтером + другие инструменты, и только если все ОК - записываем в базу и перемещаем временный файл на место исходного.

**ВАЖНО:** 
- Компилировать ВЕСЬ файл, а не только измененные части
- Проверять ВЕСЬ файл линтером, type checker и другими инструментами
- После записи в базу временный файл должен быть перемещен на место исходного (атомарная операция)

**Решение:**
1. Формировать CST узлы в памяти
2. Генерировать код из CST (весь файл)
3. Записывать во временный файл
4. Проверять ВЕСЬ файл:
   - Компиляция всего файла
   - Docstrings всего файла
   - Линтер (flake8) всего файла
   - Type checker (mypy) всего файла
   - Другие инструменты для всего файла
5. Если все проверки пройдены:
   - Начать транзакцию
   - Создать backup исходного файла
   - Обновить базу данных в транзакции (ПЕРЕД перемещением файла):
     - Сохранить CST узлы (весь файл)
     - Сохранить AST узлы (весь файл)
     - Сохранить entities (весь файл)
   - Атомарно переместить временный файл на место исходного
   - Git commit (если нужно)
   - Зафиксировать транзакцию
6. Если любая проверка не пройдена:
   - Вернуть ошибку
   - Не перемещать файл
   - Не обновлять базу

### 2.3 Откат изменений

**Требование:** Если на любом из этапов произошла ошибка - откатываем изменения.

**Решение:**
1. Использовать транзакции для отката изменений в базе
2. Использовать backup для отката изменений файла
3. Если ошибка после перемещения файла - восстановить из backup
4. Если ошибка при обновлении базы - откатить транзакцию (файл еще не перемещен)

## 3. Предлагаемое решение

### 3.1 Новый процесс `compose_cst_module`

```python
async def execute(...):
    # 1. Формирование CST узлов в памяти
    current_source = old_source
    # ... apply operations ...
    new_source = current_source
    
    # 2. Запись во временный файл
    import tempfile
    import shutil
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp_file:
        tmp_file.write(new_source)
        tmp_path = Path(tmp_file.name)
    
    try:
        # 3. Валидация ВСЕГО файла во временном файле
        # ВАЖНО: Проверяем весь файл, а не только измененные части
        
        # 3.1 Компиляция ВСЕГО файла
        ok, compile_error = compile_module(new_source, filename=str(tmp_path))
        if not ok:
            return ErrorResult(
                message="Compilation failed for entire file",
                code="COMPILE_ERROR",
                details={"compile_error": compile_error}
            )
        
        # 3.2 Docstrings - проверка ВСЕГО файла
        docstring_valid, docstring_error, docstring_errors = validate_module_docstrings(new_source)
        if not docstring_valid:
            return ErrorResult(
                message="Docstring validation failed for entire file",
                code="DOCSTRING_VALIDATION_ERROR",
                details={"docstring_errors": docstring_errors}
            )
        
        # 3.3 Линтер (flake8) - проверка ВСЕГО файла
        lint_result = run_linter(tmp_path)
        if not lint_result.success:
            return ErrorResult(
                message="Linter errors found in entire file",
                code="LINTER_ERROR",
                details={"linter_errors": lint_result.errors}
            )
        
        # 3.4 Type checker (mypy) - проверка ВСЕГО файла
        type_check_result = run_type_checker(tmp_path)
        if not type_check_result.success:
            return ErrorResult(
                message="Type checker errors found in entire file",
                code="TYPE_CHECK_ERROR",
                details={"type_check_errors": type_check_result.errors}
            )
        
        # 3.5 Другие проверки ВСЕГО файла
        # ... дополнительные проверки ...
        
        # 4. Все проверки пройдены - записываем в базу атомарно
        if apply:
            # 4.1 Начать транзакцию
            database.begin_transaction()
            backup_uuid = None
            try:
                # 4.2 Создать backup исходного файла
                backup_uuid = backup_manager.create_backup(
                    target,
                    command="compose_cst_module",
                    comment=commit_message or "",
                )
                
                # 4.3 Обновить базу данных в транзакции (ПЕРЕД перемещением файла)
                # Это гарантирует, что база обновлена с правильным содержимым
                update_result = database.update_file_data_atomic(
                    file_path=rel_path,
                    project_id=project_id,
                    root_dir=root_path,
                    source_code=new_source,  # Передаем код напрямую
                )
                
                if not update_result.get("success"):
                    raise Exception(f"Failed to update database: {update_result.get('error')}")
                
                # 4.4 Атомарное перемещение временного файла на место исходного
                # Используем atomic move для гарантии целостности
                # Если файл существует, заменяем его атомарно
                if target.exists():
                    # Создаем временный файл для атомарной замены
                    target_backup = target.with_suffix(target.suffix + '.bak')
                    target.replace(target_backup)  # Перемещаем старый файл
                    try:
                        shutil.move(str(tmp_path), str(target))  # Перемещаем новый файл
                        target_backup.unlink(missing_ok=True)  # Удаляем backup
                    except Exception:
                        # При ошибке восстанавливаем исходный файл
                        target_backup.replace(target)
                        raise
                else:
                    # Файл не существует - просто перемещаем
                    shutil.move(str(tmp_path), str(target))
                
                # 4.5 Git commit (если нужно)
                if is_git and commit_message:
                    create_git_commit(root_path, target, commit_message)
                
                # 4.6 Зафиксировать транзакцию
                database.commit_transaction()
                
                # Помечаем, что файл успешно перемещен
                tmp_path = None  # Не удалять в finally
                
            except Exception as e:
                # 4.7 Откат при ошибке
                database.rollback_transaction()
                # Восстановить файл из backup
                if backup_uuid and target.exists():
                    try:
                        backup_manager.restore_backup(target, backup_uuid)
                    except Exception as restore_error:
                        logger.error(f"Failed to restore backup: {restore_error}")
                raise
    
    finally:
        # Удалить временный файл только если он не был перемещен
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
```

### 3.2 Новый метод `update_file_data_atomic`

```python
def update_file_data_atomic(
    self,
    file_path: str,
    project_id: str,
    root_dir: Path,
    source_code: str,
) -> Dict[str, Any]:
    """
    Атомарное обновление всех данных файла в транзакции.
    
    ВАЖНО: Этот метод должен быть вызван ДО перемещения временного файла
    на место исходного. Это гарантирует, что база данных обновлена с правильным
    содержимым файла.
    
    Процесс:
    1. Найти file_id
    2. В транзакции:
       - Очистить старые данные (AST, CST, entities)
       - Парсить ВЕСЬ файл из source_code
       - Сохранить AST (весь файл)
       - Сохранить CST (весь файл)
       - Сохранить entities (весь файл)
    3. Если ошибка - откат транзакции
    
    Args:
        file_path: Путь к файлу (относительно root_dir)
        project_id: ID проекта
        root_dir: Корневая директория проекта
        source_code: Полный исходный код файла (для парсинга ВСЕГО файла)
    
    Returns:
        Результат обновления:
        {
            "success": bool,
            "file_id": int,
            "ast_updated": bool,
            "cst_updated": bool,
            "entities_updated": int,
            "error": Optional[str]
        }
    """
    # Должен быть вызван внутри транзакции
    if not self._in_transaction():
        raise RuntimeError("update_file_data_atomic must be called within a transaction")
    
    try:
        # Нормализация пути
        abs_path = normalize_path_simple(file_path)
        if not Path(abs_path).is_absolute():
            abs_path = str((Path(root_dir) / file_path).resolve())
        
        # Получить file_id
        file_record = self.get_file_by_path(abs_path, project_id)
        if not file_record:
            return {
                "success": False,
                "error": f"File not found: {file_path}",
            }
        
        file_id = file_record["id"]
        
        # Получить file_mtime (используем текущее время, т.к. файл еще не перемещен)
        import time
        file_mtime = time.time()
        
        # В транзакции:
        # 1. Очистить старые данные
        self.clear_file_data(file_id)
        
        # 2. Парсить ВЕСЬ файл
        from ..core.ast_utils import parse_with_comments
        import ast
        import json
        import hashlib
        
        try:
            tree = parse_with_comments(source_code, filename=abs_path)
        except SyntaxError as e:
            return {
                "success": False,
                "error": f"Syntax error in file: {e}",
            }
        
        # 3. Сохранить AST (весь файл)
        ast_json = json.dumps(ast.dump(tree))
        ast_hash = hashlib.sha256(ast_json.encode()).hexdigest()
        ast_tree_id = self.save_ast_tree(
            file_id,
            project_id,
            ast_json,
            ast_hash,
            file_mtime,
            overwrite=True,
        )
        
        # 4. Сохранить CST (весь файл)
        cst_hash = hashlib.sha256(source_code.encode()).hexdigest()
        cst_tree_id = self.save_cst_tree(
            file_id,
            project_id,
            source_code,
            cst_hash,
            file_mtime,
            overwrite=True,
        )
        
        # 5. Сохранить entities (весь файл)
        entities_count = self._save_entities_from_tree(
            file_id, project_id, tree, abs_path, root_dir
        )
        
        return {
            "success": True,
            "file_id": file_id,
            "ast_updated": True,
            "cst_updated": True,
            "entities_updated": entities_count,
        }
        
    except Exception as e:
        logger.error(f"Error in update_file_data_atomic: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
        }
```

### 3.3 Поддержка транзакций в базе данных

```python
def begin_transaction(self) -> None:
    """Начать транзакцию."""
    self._execute("BEGIN TRANSACTION")
    self._transaction_active = True

def commit_transaction(self) -> None:
    """Зафиксировать транзакцию."""
    if not self._transaction_active:
        raise RuntimeError("No active transaction")
    self._commit()
    self._transaction_active = False

def rollback_transaction(self) -> None:
    """Откатить транзакцию."""
    if not self._transaction_active:
        raise RuntimeError("No active transaction")
    self._rollback()
    self._transaction_active = False

def _in_transaction(self) -> bool:
    """Проверить, активна ли транзакция."""
    return getattr(self, '_transaction_active', False)
```

### 3.4 Интеграция валидации линтером

```python
def run_linter(file_path: Path) -> LintResult:
    """
    Запустить линтер (flake8) на ВСЕМ файле.
    
    ВАЖНО: Проверяет весь файл, а не только измененные части.
    """
    import subprocess
    result = subprocess.run(
        ['flake8', str(file_path)],
        capture_output=True,
        text=True,
    )
    return LintResult(
        success=result.returncode == 0,
        errors=result.stdout + result.stderr,
    )

def run_type_checker(file_path: Path) -> TypeCheckResult:
    """
    Запустить type checker (mypy) на ВСЕМ файле.
    
    ВАЖНО: Проверяет весь файл, а не только измененные части.
    """
    import subprocess
    result = subprocess.run(
        ['mypy', str(file_path)],
        capture_output=True,
        text=True,
    )
    return TypeCheckResult(
        success=result.returncode == 0,
        errors=result.stdout + result.stderr,
    )

def compile_module(source_code: str, filename: str) -> tuple[bool, Optional[str]]:
    """
    Скомпилировать ВЕСЬ модуль.
    
    ВАЖНО: Компилирует весь файл, а не только измененные части.
    
    Args:
        source_code: Полный исходный код файла
        filename: Имя файла для сообщений об ошибках
    
    Returns:
        (success, error_message)
    """
    try:
        compile(source_code, filename, 'exec')
        return True, None
    except SyntaxError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Compilation error: {e}"
```

## 4. План реализации

### Этап 1: Поддержка транзакций в базе данных
- [ ] Добавить методы `begin_transaction()`, `commit_transaction()`, `rollback_transaction()`
- [ ] Добавить проверку активной транзакции `_in_transaction()`
- [ ] Обновить драйверы базы данных для поддержки транзакций
- [ ] Протестировать транзакции

### Этап 2: Валидация во временном файле
- [ ] Добавить функцию `run_linter()` для проверки flake8
- [ ] Добавить функцию `run_type_checker()` для проверки mypy
- [ ] Добавить поддержку других инструментов проверки
- [ ] Интегрировать валидацию в `compose_cst_module`

### Этап 3: Атомарное обновление базы данных
- [ ] Создать метод `update_file_data_atomic()` с поддержкой транзакций
- [ ] Обновить `_analyze_file()` для работы в транзакции
- [ ] Обеспечить атомарность сохранения AST и CST узлов
- [ ] Протестировать атомарность

### Этап 4: Интеграция в `compose_cst_module`
- [ ] Обновить процесс для использования временного файла
- [ ] Добавить валидацию линтером перед записью
- [ ] Использовать транзакции для атомарности
- [ ] Добавить откат при ошибках
- [ ] Протестировать полный процесс

### Этап 5: Тестирование
- [ ] Написать тесты для атомарности
- [ ] Написать тесты для валидации
- [ ] Написать тесты для отката
- [ ] Интеграционные тесты

## 5. Риски и ограничения

### Риск 1: Производительность транзакций
**Проблема:** Длинные транзакции могут блокировать другие операции.

**Решение:** Минимизировать время транзакции, выполнять только критичные операции в транзакции.

### Риск 2: Поддержка транзакций в sqlite_proxy
**Проблема:** `sqlite_proxy` использует отдельные соединения для каждой операции, что может усложнить поддержку транзакций.

**Решение:** Реализовать механизм передачи контекста транзакции через сокет или использовать единое соединение для транзакции.

### Риск 3: Валидация линтером может быть медленной
**Проблема:** Запуск flake8 и mypy может занять время.

**Решение:** Оптимизировать валидацию, использовать кэширование, сделать валидацию опциональной.

## 6. Выводы

Текущая реализация имеет критические проблемы с атомарностью и валидацией. Предложенное решение обеспечивает:

1. ✅ Атомарность операций с базой данных через транзакции
2. ✅ Валидацию во временном файле перед записью
3. ✅ Проверку линтером и другими инструментами
4. ✅ Откат изменений при ошибках
5. ✅ Синхронизацию CST и AST узлов

Реализация требует изменений в нескольких компонентах системы, но критически важна для обеспечения целостности данных.

