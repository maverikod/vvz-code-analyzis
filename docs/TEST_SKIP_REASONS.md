# Причины пропуска тестов

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2026-01-09

## Обзор

Некоторые тесты пропускаются (skipped) при выполнении. Это нормальное поведение, когда тестовые данные недоступны или не соответствуют требованиям.

---

## Пропущенные тесты

### 1. `test_normalize_path_bhlff` (test_path_normalization.py)

**Статус**: ⏭️ SKIPPED

**Причина**: В директории `test_data/bhlff/` отсутствуют Python файлы (`.py`)

**Код проверки**:
```python
python_files = list(BHLFF_DIR.rglob("*.py"))
if not python_files:
    pytest.skip("No Python files found in test_data/bhlff/")
```

**Решение**:
- Тест пропускается, если в `test_data/bhlff/` нет Python файлов
- Это нормальное поведение - тест требует наличия реальных данных для проверки
- Если нужно запустить тест, добавьте Python файлы в `test_data/bhlff/`

**Примечание**: 
- Директория `test_data/bhlff/` существует
- Файл `projectid` существует и в правильном JSON формате
- Но Python файлов нет

---

### 2. `test_validate_for_bhlff_files` (test_project_id_validation.py)

**Статус**: ⏭️ SKIPPED

**Причина**: В директории `test_data/bhlff/` отсутствуют Python файлы (`.py`)

**Код проверки**:
```python
python_files = list(BHLFF_DIR.rglob("*.py"))
if not python_files:
    pytest.skip("No Python files found in test_data/bhlff/")
```

**Решение**:
- Тест пропускается, если в `test_data/bhlff/` нет Python файлов
- Это нормальное поведение - тест требует наличия реальных данных для проверки
- Если нужно запустить тест, добавьте Python файлы в `test_data/bhlff/`

**Примечание**: 
- Директория `test_data/bhlff/` существует
- Файл `projectid` существует и в правильном JSON формате
- Но Python файлов нет

---

## Другие возможные причины пропуска

### Проверка формата projectid

Тесты могут пропускаться, если `projectid` файл в старом формате (не JSON):

```python
is_old_format = not projectid_content.startswith("{")
if is_old_format:
    pytest.skip("projectid file is in old format, needs migration to JSON")
```

**Решение**: Выполнить миграцию projectid файлов (уже выполнено для всех существующих файлов)

### Отсутствие директории test_data

Тесты могут пропускаться, если директория `test_data/` не существует:

```python
if not VAST_SRV_DIR.exists():
    pytest.skip("test_data/vast_srv/ not found")
```

**Решение**: Убедиться, что директория `test_data/` существует с необходимыми поддиректориями

---

## Рекомендации

1. **Для разработки**: Пропущенные тесты не являются ошибкой - это нормальное поведение при отсутствии тестовых данных

2. **Для CI/CD**: 
   - Убедиться, что все необходимые тестовые данные присутствуют
   - Или настроить тесты так, чтобы они создавали необходимые данные при отсутствии

3. **Для полноты тестирования**:
   - Добавить Python файлы в `test_data/bhlff/` для запуска всех тестов
   - Или создать отдельные тестовые данные для этих тестов

---

## Статистика

- **Всего тестов**: 22
- **Пройдено**: 22 ✅
- **Пропущено**: 0
- **Провалено**: 0

**Обновление (2026-01-09)**:
- В `test_data/bhlff/` добавлены Python файлы (1088 файлов)
- Все тесты теперь проходят успешно
- `test_normalize_path_bhlff` - ✅ PASSED
- `test_validate_for_bhlff_files` - ✅ PASSED

---

## Вывод

Все тесты проходят успешно после добавления данных в `test_data/bhlff/`. Тесты корректно работают с реальными данными из обоих тестовых проектов (vast_srv и bhlff).

