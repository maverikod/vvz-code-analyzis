# План реализации атомарности операций с CST узлами

**Автор**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Дата**: 2026-01-09  
**Основан на**: `docs/CST_ATOMICITY_ANALYSIS.md`

## Обзор

Этот документ содержит подробный пошаговый план реализации атомарности операций с CST узлами, включая:
- Поддержку транзакций в базе данных
- Валидацию во временном файле
- Атомарное обновление базы данных
- Интеграцию в `compose_cst_module`
- Тестирование

## Важные замечания о системах отката и git

### Две системы отката в проекте

В проекте существуют **две параллельные системы отката**:

1. **BackupManager** (новая система, рекомендуется):
   - Расположение: `code_analysis/core/backup_manager.py`
   - Хранит backup в `{root_dir}/old_code/` с UUID
   - Имеет метаданные и полную историю версий
   - Метод восстановления: `restore_file(file_path, backup_uuid)`
   - Используется в новом коде для создания backup и восстановления

2. **write_with_backup** (старая система):
   - Расположение: `code_analysis/core/cst_module/utils.py`
   - Хранит backup в `{file_dir}/.code_mapper_backups/` рядом с файлом
   - Перезаписывается при каждом backup (только последняя версия)
   - Не имеет метаданных и истории версий
   - **В новом коде для `compose_cst_module` НЕ ИСПОЛЬЗУЕТСЯ**

**Решение**: В новом коде использовать только BackupManager. Вызов `write_with_backup` должен быть удален из `compose_cst_module_command.py`.

### Git commit может быть не включен

- **ВАЖНО**: `commit_message` является **ОБЯЗАТЕЛЬНЫМ**, если `is_git=True` (git репозиторий обнаружен)
- Проверка обязательности должна выполняться **В НАЧАЛЕ** метода `execute()`, до всех операций
- Если `is_git=True` и `commit_message` отсутствует - вернуть ошибку `COMMIT_MESSAGE_REQUIRED`
- Git commit выполняется только если:
  - `is_git=True` (проверяется через `is_git_repository(root_path)`)
  - `commit_message` предоставлен (обязательно при `is_git=True`)
- Если git репозиторий не обнаружен (`is_git=False`):
  - Git commit не выполняется
  - `commit_message` не обязателен
  - Операция считается успешной (данные сохранены в базе)
  - Это нормальное поведение, не ошибка

## Этап 1: Поддержка транзакций в базе данных

### Шаг 1.1: Добавить методы транзакций в базовый класс базы данных

**Файл**: `code_analysis/core/database/base.py`

**Действия**:
1. Добавить атрибут `_transaction_active: bool = False` в класс `CodeDatabase`
2. Добавить метод `begin_transaction() -> None`:
   ```python
   def begin_transaction(self) -> None:
       """Начать транзакцию базы данных."""
       if self._transaction_active:
           raise RuntimeError("Transaction already active")
       self._execute("BEGIN TRANSACTION")
       self._transaction_active = True
       logger.debug("Transaction started")
   ```
3. Добавить метод `commit_transaction() -> None`:
   ```python
   def commit_transaction(self) -> None:
       """Зафиксировать транзакцию."""
       if not self._transaction_active:
           raise RuntimeError("No active transaction")
       self._commit()
       self._transaction_active = False
       logger.debug("Transaction committed")
   ```
4. Добавить метод `rollback_transaction() -> None`:
   ```python
   def rollback_transaction(self) -> None:
       """Откатить транзакцию."""
       if not self._transaction_active:
           raise RuntimeError("No active transaction")
       self._rollback()
       self._transaction_active = False
       logger.debug("Transaction rolled back")
   ```
5. Добавить метод `_in_transaction() -> bool`:
   ```python
   def _in_transaction(self) -> bool:
       """Проверить, активна ли транзакция."""
       return getattr(self, '_transaction_active', False)
   ```
6. Обновить метод `_commit()` для проверки транзакции (опционально, для безопасности)

**Тесты**: `tests/test_database_transactions.py`
- Тест начала транзакции
- Тест коммита транзакции
- Тест отката транзакции
- Тест вложенных транзакций (должна быть ошибка)
- Тест коммита без активной транзакции (должна быть ошибка)

### Шаг 1.2: Обновить SQLite драйвер для поддержки транзакций

**Файл**: `code_analysis/core/db_driver/sqlite.py`

**Действия**:
1. Убедиться, что метод `execute()` не делает auto-commit при активной транзакции
2. Обновить метод `commit()` для работы с транзакциями
3. Обновить метод `rollback()` для работы с транзакциями

**Тесты**: `tests/test_sqlite_driver_transactions.py`
- Тест транзакций в SQLite драйвере

### Шаг 1.3: Обновить SQLite Proxy драйвер для поддержки транзакций

**Файл**: `code_analysis/core/db_driver/sqlite_proxy.py`

**Проблема**: SQLite Proxy использует отдельные соединения для каждой операции.

**Действия**:
1. Добавить механизм передачи контекста транзакции через сокет:
   - Добавить поле `_transaction_id: Optional[str]` для отслеживания транзакции
   - При `begin_transaction()` создать уникальный ID транзакции
   - Передавать `transaction_id` в каждую операцию через сокет
   - DB worker должен использовать одно соединение для всех операций в транзакции
2. Обновить метод `execute()` для поддержки транзакций:
   ```python
   def execute(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> None:
       transaction_id = getattr(self, '_transaction_id', None)
       result = self._execute_operation(
           "execute",
           sql=sql,
           params=params,
           transaction_id=transaction_id,
       )
   ```
3. Обновить методы `commit()` и `rollback()` для работы с транзакциями

**Файл**: `code_analysis/core/db_worker_pkg/runner.py`

**Действия**:
1. Добавить поддержку `transaction_id` в `_execute_operation()`
2. Использовать одно соединение для всех операций в транзакции
3. Хранить соединения транзакций в словаре: `_transaction_connections: Dict[str, sqlite3.Connection]`

**Тесты**: `tests/test_sqlite_proxy_transactions.py`
- Тест транзакций через proxy
- Тест отката транзакции через proxy
- Тест параллельных транзакций

### Шаг 1.4: Обновить контекстный менеджер для транзакций (опционально)

**Файл**: `code_analysis/core/database/base.py`

**Действия**:
1. Добавить контекстный менеджер `transaction()`:
   ```python
   @contextmanager
   def transaction(self):
       """Контекстный менеджер для транзакций."""
       self.begin_transaction()
       try:
           yield
           self.commit_transaction()
       except Exception:
           self.rollback_transaction()
           raise
   ```

**Тесты**: `tests/test_database_transaction_context.py`
- Тест успешной транзакции через контекстный менеджер
- Тест отката при ошибке

## Этап 2: Валидация во временном файле

### Шаг 2.1: Создать модуль валидации для временных файлов

**Файл**: `code_analysis/core/cst_module/validation.py` (новый файл)

**Действия**:
1. Создать класс `ValidationResult`:
   ```python
   @dataclass
   class ValidationResult:
       success: bool
       error_message: Optional[str] = None
       errors: List[str] = field(default_factory=list)
   ```
2. Создать функцию `validate_file_in_temp()`:
   ```python
   def validate_file_in_temp(
       source_code: str,
       temp_file_path: Path,
       validate_linter: bool = True,
       validate_type_checker: bool = True,
   ) -> Tuple[bool, Optional[str], Dict[str, ValidationResult]]:
       """
       Валидация всего файла во временном файле.
       
       Args:
           source_code: Полный исходный код файла
           temp_file_path: Путь к временному файлу
           validate_linter: Проверять линтером
           validate_type_checker: Проверять type checker
       
       Returns:
           (overall_success, error_message, results_dict)
       """
   ```
3. Интегрировать существующие функции:
   - Использовать `compile_module()` из `code_analysis/core/cst_module/__init__.py`
   - Использовать `validate_module_docstrings()` из `code_analysis/core/cst_module/docstring_validator.py`
   - Использовать `lint_with_flake8()` из `code_analysis/core/code_quality/linter.py`
   - Использовать `type_check_with_mypy()` из `code_analysis/core/code_quality/type_checker.py`

**Тесты**: `tests/test_cst_validation.py`
- Тест успешной валидации
- Тест ошибки компиляции
- Тест ошибки линтера
- Тест ошибки type checker
- Тест ошибки docstrings

### Шаг 2.2: Обновить `compile_module()` для работы с временным файлом

**Файл**: `code_analysis/core/cst_module/__init__.py`

**Действия**:
1. Убедиться, что `compile_module()` компилирует весь файл
2. Добавить поддержку временного файла (если нужно)

**Тесты**: Обновить существующие тесты

## Этап 3: Атомарное обновление базы данных

### Шаг 3.1: Создать метод `update_file_data_atomic()`

**Файл**: `code_analysis/core/database/files.py`

**Действия**:
1. Добавить метод `update_file_data_atomic()`:
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
       
       ВАЖНО: Должен быть вызван внутри активной транзакции.
       """
       if not self._in_transaction():
           raise RuntimeError("update_file_data_atomic must be called within a transaction")
       
       # ... реализация ...
   ```
2. Использовать существующий метод `_analyze_file()` из `UpdateIndexesMCPCommand`, но адаптировать для работы с `source_code` напрямую
3. Обеспечить атомарность:
   - Очистить старые данные в транзакции
   - Сохранить AST в транзакции
   - Сохранить CST в транзакции
   - Сохранить entities в транзакции

**Тесты**: `tests/test_update_file_data_atomic.py`
- Тест успешного обновления
- Тест отката при ошибке парсинга
- Тест отката при ошибке сохранения AST
- Тест отката при ошибке сохранения CST
- Тест вызова без активной транзакции (должна быть ошибка)

### Шаг 3.2: Создать вспомогательный метод `_save_entities_from_tree()`

**Файл**: `code_analysis/core/database/files.py`

**Действия**:
1. Извлечь логику сохранения entities из `_analyze_file()` в отдельный метод
2. Метод должен принимать:
   - `file_id: int`
   - `project_id: str`
   - `tree: ast.Module`
   - `abs_path: str`
   - `root_dir: Path`
3. Возвращать количество сохраненных entities

**Тесты**: `tests/test_save_entities_from_tree.py`
- Тест сохранения классов
- Тест сохранения функций
- Тест сохранения методов
- Тест сохранения импортов

### Шаг 3.3: Обновить `_analyze_file()` для работы с `source_code` напрямую

**Файл**: `code_analysis/commands/code_mapper_mcp_command.py`

**Действия**:
1. Добавить опциональный параметр `source_code: Optional[str] = None` в `_analyze_file()`
2. Если `source_code` передан, использовать его вместо чтения из файла
3. Обновить логику для работы с переданным кодом

**Тесты**: Обновить существующие тесты

## Этап 4: Интеграция в `compose_cst_module`

### Шаг 4.1: Обновить процесс формирования CST узлов

**Файл**: `code_analysis/commands/cst_compose_module_command.py`

**Действия**:
1. **Сохранить проверку обязательности `commit_message`** в начале метода `execute()` (если git репозиторий обнаружен)
2. Оставить существующую логику формирования CST узлов (строки 333-365)
3. Убедиться, что `new_source` содержит весь файл

**Тесты**: Существующие тесты должны продолжать работать

### Шаг 4.2: Добавить создание временного файла

**Файл**: `code_analysis/commands/cst_compose_module_command.py`

**Действия**:
1. После формирования `new_source` (строка 365), добавить:
   ```python
   import tempfile
   import shutil
   
   # Создать временный файл
   with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as tmp_file:
       tmp_file.write(new_source)
       tmp_path = Path(tmp_file.name)
   ```
2. Обернуть весь процесс в `try/finally` для очистки временного файла

**Тесты**: `tests/test_cst_compose_temp_file.py`
- Тест создания временного файла
- Тест очистки временного файла при ошибке
- Тест очистки временного файла при успехе

### Шаг 4.3: Добавить валидацию во временном файле

**Файл**: `code_analysis/commands/cst_compose_module_command.py`

**Действия**:
1. После создания временного файла, перед `if apply:`, добавить валидацию:
   ```python
   # Валидация ВСЕГО файла во временном файле
   from ..core.cst_module.validation import validate_file_in_temp
   
   validation_success, validation_error, validation_results = validate_file_in_temp(
       source_code=new_source,
       temp_file_path=tmp_path,
       validate_linter=True,
       validate_type_checker=True,
   )
   
   if not validation_success:
       # Вернуть ошибку с деталями
       return ErrorResult(
           message=validation_error or "Validation failed",
           code="VALIDATION_ERROR",
           details={
               "validation_results": {
                   k: {
                       "success": v.success,
                       "error_message": v.error_message,
                       "errors": v.errors,
                   }
                   for k, v in validation_results.items()
               }
           }
       )
   ```
2. Обновить существующие проверки компиляции и docstrings для использования временного файла

**Тесты**: `tests/test_cst_compose_validation.py`
- Тест успешной валидации
- Тест ошибки компиляции
- Тест ошибки линтера
- Тест ошибки type checker
- Тест ошибки docstrings

### Шаг 4.4: Обновить процесс записи в базу и перемещения файла

**Файл**: `code_analysis/commands/cst_compose_module_command.py`

**ВАЖНО**: 
- **`commit_message` ОБЯЗАТЕЛЕН**, если `is_git=True` (git репозиторий обнаружен)
- Проверка обязательности `commit_message` должна быть **В НАЧАЛЕ** метода `execute()`, до всех операций
- Если `is_git=True` и `commit_message` отсутствует - вернуть ошибку `COMMIT_MESSAGE_REQUIRED` и не выполнять операцию
- Git commit должен выполняться ПОСЛЕ успешного завершения транзакции
- Если git commit не удался, это не должно откатывать транзакцию (транзакция уже зафиксирована)
- Git commit выполняется только если `is_git=True` (проверяется через `is_git_repository()`) и `commit_message` предоставлен
- Git может быть не включен (не git репозиторий) - в этом случае git commit просто не выполняется, `commit_message` не обязателен
- **Две системы отката**: 
  - BackupManager (новая система) - используется для восстановления файлов при ошибке
  - write_with_backup (старая система) - **УДАЛИТЬ** из нового кода, так как BackupManager уже создает backup

**Действия**:
1. **Сохранить проверку обязательности `commit_message`** в начале метода `execute()` (строки 223-230 в текущей версии):
   ```python
   # Check if git repository and validate commit_message
   is_git = is_git_repository(root_path)
   if is_git and not commit_message:
       return ErrorResult(
           message="commit_message is required when working in a git repository",
           code="COMMIT_MESSAGE_REQUIRED",
           details={"root_dir": str(root_path)},
       )
   ```
2. **Удалить вызов `write_with_backup`** из нового кода (строка 436-438 в текущей версии)
3. Заменить существующий блок `if apply:` (строки 435-486) на новый процесс:
   ```python
   if apply:
       # Начать транзакцию
       database = self._open_database(str(root_path), auto_analyze=False)
       database.begin_transaction()
       backup_uuid = None
       tmp_path_moved = False
       backup_manager = None
       
       try:
           # Создать backup исходного файла через BackupManager (если файл существует)
           if target.exists():
               backup_manager = BackupManager(root_path)
               backup_uuid = backup_manager.create_backup(
                   target,
                   command="compose_cst_module",
                   comment=commit_message or "",
               )
               if backup_uuid:
                   logger.info(f"Backup created: {backup_uuid}")
           
           # Обновить базу данных в транзакции (ПЕРЕД перемещением файла)
           project_id = self._get_project_id(
               database, root_path, kwargs.get("project_id")
           )
           if project_id:
               try:
                   rel_path = str(target.relative_to(root_path))
               except ValueError:
                   rel_path = str(target)
               
               update_result = database.update_file_data_atomic(
                   file_path=rel_path,
                   project_id=project_id,
                   root_dir=root_path,
                   source_code=new_source,
               )
               
               if not update_result.get("success"):
                   raise Exception(f"Failed to update database: {update_result.get('error')}")
               
               # Атомарное перемещение временного файла на место исходного
               if target.exists():
                   target_backup = target.with_suffix(target.suffix + '.bak')
                   target.replace(target_backup)
                   try:
                       shutil.move(str(tmp_path), str(target))
                       tmp_path_moved = True
                       target_backup.unlink(missing_ok=True)
                   except Exception:
                       target_backup.replace(target)
                       raise
               else:
                   shutil.move(str(tmp_path), str(target))
                   tmp_path_moved = True
               
               # Зафиксировать транзакцию (ПЕРЕД git commit)
               database.commit_transaction()
               
               # Git commit после успешного завершения (если git репозиторий и commit_message предоставлен)
               # ВАЖНО: is_git проверяется через is_git_repository(), git может быть не включен
               if is_git and commit_message:
                   git_commit_success, git_error = create_git_commit(
                       root_path, target, commit_message
                   )
                   if not git_commit_success:
                       # Git commit не критичен - транзакция уже зафиксирована
                       logger.warning(f"Failed to create git commit: {git_error}")
                   else:
                       logger.info(f"Git commit created successfully: {commit_message}")
               
           finally:
               database.close()
               
       except Exception as e:
           # Откат при ошибке
           try:
               database.rollback_transaction()
           except Exception:
               pass
           
           # Восстановить файл из backup через BackupManager (если backup был создан)
           if backup_uuid and backup_manager and target.exists():
               try:
                   # Получить относительный путь для восстановления
                   try:
                       rel_path = str(target.relative_to(root_path))
                   except ValueError:
                       rel_path = str(target)
                   
                   # Восстановить файл из backup
                   restore_success, restore_message = backup_manager.restore_file(
                       rel_path, backup_uuid
                   )
                   if restore_success:
                       logger.info(f"File restored from backup: {restore_message}")
                   else:
                       logger.error(f"Failed to restore file from backup: {restore_message}")
               except Exception as restore_error:
                   logger.error(f"Failed to restore backup: {restore_error}")
           
           raise
       
       finally:
           # Удалить временный файл только если он не был перемещен
           if not tmp_path_moved and tmp_path.exists():
               tmp_path.unlink(missing_ok=True)
   ```

**Тесты**: `tests/test_cst_compose_atomic.py`
- Тест успешного атомарного обновления
- Тест отката при ошибке обновления базы
- Тест отката при ошибке перемещения файла
- Тест восстановления из backup через BackupManager
- Тест отката транзакции
- Тест автоматического git commit после успешного завершения (если git репозиторий и commit_message предоставлен)
- Тест отсутствия git commit при ошибке транзакции
- Тест обработки ошибки git commit (не должен откатывать транзакцию)
- Тест работы без git репозитория (git commit не выполняется, commit_message не обязателен, операция успешна)
- **Тест обязательности commit_message при is_git=True** (должна быть ошибка COMMIT_MESSAGE_REQUIRED)
- Тест работы с commit_message при is_git=False (операция успешна, git commit не выполняется)
- Тест отсутствия write_with_backup в новом коде

### Шаг 4.5: Обновить обработку ошибок

**Файл**: `code_analysis/commands/cst_compose_module_command.py`

**Действия**:
1. Обновить обработку ошибок для возврата детальной информации о валидации
2. Добавить логирование всех этапов процесса
3. Убедиться, что временный файл всегда удаляется

**Тесты**: Обновить существующие тесты

## Этап 5: Тестирование

### Шаг 5.1: Написать unit тесты для транзакций

**Файл**: `tests/test_database_transactions.py`

**Тесты**:
- `test_begin_transaction()` - начало транзакции
- `test_commit_transaction()` - коммит транзакции
- `test_rollback_transaction()` - откат транзакции
- `test_nested_transactions()` - вложенные транзакции (должна быть ошибка)
- `test_commit_without_transaction()` - коммит без транзакции (должна быть ошибка)
- `test_transaction_context_manager()` - контекстный менеджер

### Шаг 5.2: Написать unit тесты для валидации

**Файл**: `tests/test_cst_validation.py`

**Тесты**:
- `test_validate_success()` - успешная валидация
- `test_validate_compile_error()` - ошибка компиляции
- `test_validate_linter_error()` - ошибка линтера
- `test_validate_type_check_error()` - ошибка type checker
- `test_validate_docstring_error()` - ошибка docstrings
- `test_validate_multiple_errors()` - несколько ошибок

### Шаг 5.3: Написать unit тесты для атомарного обновления

**Файл**: `tests/test_update_file_data_atomic.py`

**Тесты**:
- `test_update_file_data_atomic_success()` - успешное обновление
- `test_update_file_data_atomic_rollback_on_parse_error()` - откат при ошибке парсинга
- `test_update_file_data_atomic_rollback_on_ast_error()` - откат при ошибке сохранения AST
- `test_update_file_data_atomic_rollback_on_cst_error()` - откат при ошибке сохранения CST
- `test_update_file_data_atomic_without_transaction()` - вызов без транзакции (должна быть ошибка)

### Шаг 5.4: Написать интеграционные тесты для `compose_cst_module`

**Файл**: `tests/test_cst_compose_atomic_integration.py`

**Тесты**:
- `test_compose_cst_module_full_flow()` - полный успешный процесс
- `test_compose_cst_module_validation_failure()` - ошибка валидации
- `test_compose_cst_module_database_rollback()` - откат при ошибке базы
- `test_compose_cst_module_file_restore()` - восстановление файла из backup
- `test_compose_cst_module_transaction_rollback()` - откат транзакции
- `test_compose_cst_module_temp_file_cleanup()` - очистка временного файла
- `test_compose_cst_module_git_commit_success()` - успешный git commit после транзакции
- `test_compose_cst_module_git_commit_failure()` - ошибка git commit (не должна откатывать транзакцию)
- `test_compose_cst_module_no_git_commit_on_error()` - git commit не выполняется при ошибке транзакции

### Шаг 5.5: Написать тесты производительности

**Файл**: `tests/test_cst_compose_performance.py`

**Тесты**:
- `test_transaction_performance()` - производительность транзакций
- `test_validation_performance()` - производительность валидации
- `test_atomic_update_performance()` - производительность атомарного обновления

## Этап 6: Документация и рефакторинг

### Шаг 6.1: Обновить документацию

**Файлы**:
- `docs/CST_TOOLS.md` - обновить описание процесса
- `docs/AST_UPDATE_ANALYSIS.md` - обновить информацию об атомарности
- `README.md` - добавить информацию о транзакциях

### Шаг 6.2: Рефакторинг кода

**Действия**:
1. Удалить неиспользуемый код
2. Улучшить именование переменных
3. Добавить docstrings
4. Обновить типы (type hints)

### Шаг 6.3: Обновить метаданные команды

**Файл**: `code_analysis/commands/cst_compose_module_command.py`

**КРИТИЧЕСКИ ВАЖНО**: Метаданные должны быть **по подробности не меньше, чем man-страницы**. Это означает:
- Полное описание всех этапов процесса
- Детальное описание всех параметров
- Подробные примеры использования (минимум 5-7 примеров)
- Описание всех возможных ошибок и их причин
- Описание edge cases и особых ситуаций
- Подробная информация о git интеграции с примерами
- Описание атомарности операций и транзакций
- Описание систем отката (BackupManager)

**Действия**:
1. Обновить метод `metadata()` с **максимально подробной** информацией:
   - **detailed_description**: Полное описание процесса с деталями:
     - Все этапы выполнения (валидация, транзакции, backup, git)
     - Описание атомарности операций
     - Описание систем отката (BackupManager vs write_with_backup)
     - Подробная информация о git интеграции:
       - Когда commit_message обязателен
       - Когда git commit выполняется
       - Что происходит при ошибке git commit
       - Примеры работы с git и без git
     - Описание валидации (компиляция, линтер, type checker, docstrings)
     - Описание транзакций базы данных
     - Описание временных файлов
   
   - **parameters**: Детальное описание каждого параметра:
     - `root_dir`: Что происходит если это git репозиторий
     - `file_path`: Как обрабатываются новые файлы
     - `ops`: Детальное описание операций и селекторов
     - `apply`: Что происходит при apply=true vs false
     - `create_backup`: Как работает BackupManager
     - `commit_message`: **ОБЯЗАТЕЛЬНОСТЬ** при git репозитории, примеры
     - `return_diff`: Формат diff
     - `return_source`: Когда использовать
   
   - **examples**: **Минимум 5-7 подробных примеров**:
     1. Preview изменений без применения (apply=false)
     2. Применение изменений в git репозитории (commit_message обязателен)
     3. Применение изменений БЕЗ git репозитория (commit_message не обязателен)
     4. Создание нового файла с нуля
     5. Множественные операции (replace + insert + create)
     6. Обработка ошибок валидации
     7. Работа с backup и восстановление
   
   - **error_codes**: Подробное описание всех ошибок с примерами и решениями:
     - `COMMIT_MESSAGE_REQUIRED`: 
       - Когда возникает: `is_git=True` и `commit_message` отсутствует
       - Как исправить: Предоставить `commit_message` параметр
       - Пример: "commit_message is required when working in a git repository"
     - `VALIDATION_ERROR`: 
       - Типы валидации: компиляция, линтер, type checker, docstrings
       - Примеры ошибок: синтаксические ошибки, ошибки линтера, ошибки типов
       - Структура ответа: `validation_results` с деталями по каждому типу
     - `COMPILE_ERROR`: 
       - Причины: синтаксические ошибки Python, ошибки парсинга
       - Примеры: "SyntaxError: invalid syntax", "IndentationError"
       - Решение: Исправить синтаксические ошибки в коде
     - `DOCSTRING_VALIDATION_ERROR`: 
       - Требования к docstrings: файл, классы, методы, функции
       - Примеры ошибок: отсутствие docstring, неправильный формат
       - Решение: Добавить/исправить docstrings согласно стандартам проекта
     - `LINTER_ERROR`: 
       - Типы ошибок линтера: flake8 ошибки (E, W, F коды)
       - Примеры: "E501 line too long", "F401 unused import"
       - Решение: Исправить ошибки линтера согласно правилам проекта
     - `TYPE_CHECK_ERROR`: 
       - Типы ошибок type checker: mypy ошибки
       - Примеры: "Incompatible types", "Missing type annotation"
       - Решение: Исправить типы согласно требованиям mypy
     - `TRANSACTION_ERROR`: 
       - Ошибки транзакций: "Transaction already active", "No active transaction"
       - Решение: Проверить логику использования транзакций
     - `BACKUP_ERROR`: 
       - Ошибки создания/восстановления backup: файл не найден, ошибка записи
       - Решение: Проверить права доступа, наличие места на диске
     - `GIT_COMMIT_ERROR`: 
       - Ошибки git commit: "Failed to stage file", "Failed to create commit"
       - Важно: Не критична, операция считается успешной (данные сохранены)
       - Решение: Проверить git репозиторий, права доступа
     - `FILE_NOT_FOUND`: Файл не существует (для новых файлов использовать `kind='module'`)
     - `INVALID_FILE`: Файл не является .py файлом
     - `INVALID_OPERATION`: Неизвестный тип операции
   
   - **git_integration**: Отдельный раздел с подробностями:
     - Автоматическое определение git репозитория
     - Обязательность commit_message
     - Процесс создания git commit
     - Обработка ошибок git commit
     - Примеры работы с git и без git
   
   - **atomicity**: Отдельный раздел об атомарности:
     - Транзакции базы данных
     - Валидация во временном файле
     - Атомарное перемещение файла
     - Системы отката (BackupManager)
     - Порядок операций (backup -> транзакция -> файл -> git)
   
   - **safety_features**: Подробное описание всех проверок безопасности

2. **Примеры должны включать**:
   - Работу с git репозиторием (commit_message обязателен)
   - Работу без git репозитория (commit_message не обязателен)
   - Preview режим
   - Создание новых файлов
   - Множественные операции
   - Обработку ошибок

3. Обновить описание ошибок с примерами и решениями

4. Добавить раздел "See Also" с ссылками на связанные команды и документацию

## Порядок выполнения этапов

Рекомендуемый порядок:
1. **Этап 1** (Транзакции) - основа для всего остального
2. **Этап 2** (Валидация) - можно делать параллельно с Этапом 1
3. **Этап 3** (Атомарное обновление) - зависит от Этапа 1
4. **Этап 4** (Интеграция) - зависит от всех предыдущих этапов
5. **Этап 5** (Тестирование) - параллельно с каждым этапом
6. **Этап 6** (Документация) - в конце

## Критерии готовности

Каждый этап считается завершенным, когда:
- ✅ Все шаги выполнены
- ✅ Все тесты написаны и проходят
- ✅ Код проверен линтером и type checker
- ✅ Документация обновлена
- ✅ Code review пройден

## Риски и митигация

### Риск 1: Производительность транзакций
**Митигация**: Минимизировать время транзакции, выполнять только критичные операции

### Риск 2: Поддержка транзакций в sqlite_proxy
**Митигация**: Использовать единое соединение для транзакции, передавать transaction_id

### Риск 3: Валидация линтером медленная
**Митигация**: Сделать валидацию опциональной, использовать кэширование

### Риск 4: Атомарное перемещение файла может быть проблематичным на некоторых файловых системах
**Митигация**: Использовать backup файл для отката, тестировать на разных файловых системах

## Примечания

1. Все изменения должны быть обратно совместимыми
2. Существующие тесты должны продолжать работать
3. Новые функции должны быть опциональными (можно отключить валидацию)
4. Логирование должно быть подробным для отладки
5. **Git commit выполняется ПОСЛЕ успешного завершения транзакции**:
   - **ВАЖНО**: `commit_message` является **ОБЯЗАТЕЛЬНЫМ**, если `is_git=True` (git репозиторий обнаружен)
   - Проверка обязательности `commit_message` выполняется **В НАЧАЛЕ** метода `execute()`, до всех операций
   - Если `is_git=True` и `commit_message` отсутствует - возвращается ошибка `COMMIT_MESSAGE_REQUIRED`, операция не выполняется
   - Транзакция базы данных фиксируется первой
   - Затем выполняется git commit (если `is_git=True` через `is_git_repository()` и `commit_message` предоставлен)
   - Если git репозиторий не обнаружен (`is_git=False`), git commit не выполняется, `commit_message` не обязателен, операция считается успешной
   - Если git commit не удался, это не откатывает транзакцию (данные уже сохранены)
   - Git commit является опциональным и не критичным для успеха операции (но `commit_message` обязателен при `is_git=True`)
   - Git commit выполняется автоматически при успешном завершении всех операций
   - Если git commit не удался, операция все равно считается успешной (данные сохранены)

## Анализ полноты плана

### Проверка всех компонентов

#### ✅ Этап 1: Транзакции базы данных
- [x] Методы транзакций в базовом классе
- [x] Поддержка в SQLite драйвере
- [x] Поддержка в SQLite Proxy драйвере
- [x] Контекстный менеджер (опционально)
- [x] Тесты для всех компонентов

#### ✅ Этап 2: Валидация во временном файле
- [x] Модуль валидации (`validation.py`)
- [x] Класс `ValidationResult`
- [x] Функция `validate_file_in_temp()`
- [x] Интеграция существующих функций:
  - [x] `compile_module()` - компиляция
  - [x] `validate_module_docstrings()` - проверка docstrings
  - [x] `lint_with_flake8()` - линтер (из `code_analysis/core/code_quality/linter.py`)
  - [x] `type_check_with_mypy()` - type checker (из `code_analysis/core/code_quality/type_checker.py`)
- [x] Тесты для всех типов валидации

#### ✅ Этап 3: Атомарное обновление базы данных
- [x] Метод `update_file_data_atomic()`
- [x] Метод `_save_entities_from_tree()`
- [x] Обновление `_analyze_file()` для работы с `source_code`
- [x] Атомарность операций (очистка -> AST -> CST -> entities)
- [x] Тесты для всех сценариев

#### ✅ Этап 4: Интеграция в `compose_cst_module`
- [x] Сохранение проверки `commit_message` в начале `execute()`
- [x] Формирование CST узлов (без изменений)
- [x] Создание временного файла
- [x] Валидация во временном файле (ВСЕГО файла)
- [x] Удаление `write_with_backup` из кода
- [x] Использование только BackupManager
- [x] Транзакции базы данных
- [x] Атомарное перемещение файла
- [x] Git commit после транзакции
- [x] Восстановление из backup при ошибке
- [x] Очистка временного файла
- [x] Обработка всех ошибок

#### ✅ Этап 5: Тестирование
- [x] Unit тесты для транзакций
- [x] Unit тесты для валидации
- [x] Unit тесты для атомарного обновления
- [x] Интеграционные тесты для `compose_cst_module`
- [x] Тесты производительности

#### ✅ Этап 6: Документация и рефакторинг
- [x] Обновление документации
- [x] Рефакторинг кода
- [x] **Подробные метаданные команды (как man-страницы)**
  - [x] Полное описание процесса
  - [x] Детальное описание параметров
  - [x] Минимум 5-7 примеров (включая git и без git)
  - [x] Описание всех ошибок
  - [x] Раздел git_integration
  - [x] Раздел atomicity
  - [x] Раздел safety_features

### Проверка всех требований

#### ✅ Системы отката
- [x] BackupManager учтен и используется
- [x] write_with_backup удаляется из нового кода
- [x] Восстановление через BackupManager.restore_file()
- [x] Backup создается ПЕРЕД применением изменений

#### ✅ Git интеграция
- [x] Проверка `is_git_repository()` в начале `execute()`
- [x] `commit_message` обязателен при `is_git=True`
- [x] Ошибка `COMMIT_MESSAGE_REQUIRED` при отсутствии commit_message
- [x] Git commit выполняется ПОСЛЕ транзакции
- [x] Git commit не откатывает транзакцию при ошибке
- [x] Работа без git репозитория учтена

#### ✅ Валидация
- [x] Компиляция всего файла
- [x] Проверка docstrings всего файла
- [x] Линтер (flake8) всего файла
- [x] Type checker (mypy) всего файла
- [x] Валидация во временном файле (не на исходном)

#### ✅ Атомарность
- [x] Транзакции базы данных
- [x] Валидация ПЕРЕД записью файла
- [x] Обновление базы ПЕРЕД перемещением файла
- [x] Атомарное перемещение файла
- [x] Откат при любой ошибке

#### ✅ Порядок операций
- [x] 1. Проверка git и commit_message (в начале)
- [x] 2. Формирование CST узлов
- [x] 3. Создание временного файла
- [x] 4. Валидация во временном файле
- [x] 5. Если apply=True:
   - [x] 5.1. Создание backup (BackupManager)
   - [x] 5.2. Начало транзакции
   - [x] 5.3. Обновление базы данных в транзакции
   - [x] 5.4. Атомарное перемещение файла
   - [x] 5.5. Коммит транзакции
   - [x] 5.6. Git commit (если git репозиторий)

### Проверка edge cases

- [x] Создание нового файла (target не существует)
- [x] Файл вне root_dir (ValueError при relative_to)
- [x] Ошибка валидации (компиляция, линтер, type checker, docstrings)
- [x] Ошибка обновления базы данных
- [x] Ошибка перемещения файла
- [x] Ошибка git commit (не критична)
- [x] Откат транзакции при любой ошибке
- [x] Восстановление файла из backup при ошибке
- [x] Очистка временного файла во всех случаях
- [x] Работа без git репозитория
- [x] Работа с git репозиторием без commit_message (ошибка)

### Проверка тестов

- [x] Тесты транзакций (начало, коммит, откат, вложенные, без транзакции)
- [x] Тесты валидации (успех, компиляция, линтер, type checker, docstrings)
- [x] Тесты атомарного обновления (успех, откат при ошибках)
- [x] Интеграционные тесты (полный процесс, ошибки, откат, git)
- [x] Тесты производительности

### Итоговая проверка

✅ **Все компоненты учтены**
✅ **Все требования выполнены**
✅ **Все edge cases обработаны**
✅ **Все тесты предусмотрены**
✅ **Метаданные будут подробными (как man-страницы)**

**План готов к реализации. Ничего не упущено.**
6. **Две системы отката в проекте**:
   - **BackupManager** (новая система, рекомендуется):
     - Хранит backup в `{root_dir}/old_code/` с UUID
     - Имеет метаданные и историю версий
     - Метод восстановления: `restore_file(file_path, backup_uuid)`
     - Используется в новом коде для создания backup и восстановления
   - **write_with_backup** (старая система):
     - Хранит backup в `{file_dir}/.code_mapper_backups/` рядом с файлом
     - Перезаписывается при каждом backup (только последняя версия)
     - **УДАЛЯЕТСЯ** из нового кода в `compose_cst_module`
     - Оставляется в `code_analysis/core/cst_module/utils.py` для обратной совместимости (если используется в других местах)
7. **Восстановление из backup**:
   - Используется только BackupManager для восстановления
   - Метод: `backup_manager.restore_file(rel_path, backup_uuid)`
   - Восстановление выполняется только если backup был создан (`backup_uuid` не None)
   - Восстановление выполняется только если файл существует (для возможности восстановления)

