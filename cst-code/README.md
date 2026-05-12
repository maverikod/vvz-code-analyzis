# cst-code — снимок подсистем **CST + AST** code-analysis

Каталог **`cst-code/`** в корне репозитория — **копия** исходников для работы с Python на двух уровнях:

| Уровень | Роль | Типичное использование |
|--------|------|-------------------------|
| **AST** (`ast` / БД) | Структура, индекс, запросы, «обзор без round-trip» | `get_ast`, `search_ast_nodes`, статистика, сущности, графы |
| **CST** (LibCST) | Сохранение форматирования, комментариев, точные правки | `cst_load_file`, `cst_modify_tree`, селекторы, sidecar `.cst/*.tree` |

**Стабильные идентификаторы (`stable_id`)** в CST-слое привязаны к **данным сущности** (и персистятся в исходнике там, где поддерживается), а не к ephemeral `node_id` сессии — это мост между «посмотрел по AST/индексу» и «открыл дерево для правки».

Цель снимка: вынести **редактирование (CST)** в отдельный сервис/пакет, оставив в сервере анализа **AST**, **семантику** и **полнотекст**, при этом иметь в одном месте **полный комплект** исходников для переноса. Это **не** готовый `pip install` без доработки проводки (БД, бэкапы, `BaseMCPCommand`, конфиг).

---

## Состав

### 1. CST (редактирование и запросы по дереву)

| Путь | Назначение |
|------|------------|
| `code_analysis/core/cst_tree/` | Загрузка/кэш деревьев, модификация, сохранение, sidecar, `stable_id`, верификация записи |
| `code_analysis/core/cst_module/` | Патчи LibCST: `ReplaceOp` / `Selector`, `list_cst_blocks`, валидация |
| `code_analysis/core/mutable_cst/` | Альтернативный путь правок, связанный с деревом |
| `code_analysis/cst_query/` | Парсер и исполнение селекторов (`parse_selector`, `query_source`, `QueryParseError`); модуль `cst_query/ast.py` — связка запросов с CST |
| `code_analysis/core/exceptions.py` | В т.ч. CST- и docstring/selector-исключения |

Команды MCP и compose: `cst_*`, `query_cst*`, `list_cst_blocks*`, `compose_cst*`, `line_command_cst_gate.py`, `project_text_file_guard.py` — в `code_analysis/commands/` (см. `FILE_LIST.txt`).

### 2. AST (просмотр, индекс, команды MCP)

| Путь | Назначение |
|------|------------|
| `code_analysis/core/ast_utils.py` | Парсинг с учётом комментариев / вспомогательные утилиты для пайплайна индексации |
| `code_analysis/core/database/ast.py` | Слой БД для сохранения/чтения сериализованного AST (`ast_trees` и связанная логика) |
| `code_analysis/commands/ast/` | **Полный набор** MCP-команд категории `ast`: `get_ast`, `search_ast_nodes`, `ast_statistics`, сущности, импорты, зависимости, графы, иерархии, `list_project_files` для AST и др. |

Импорты внутри по-прежнему рассчитаны на пакет **`code_analysis`** в монорепозитории. Для отдельного репозитория обычно переименовывают корень или настраивают `PYTHONPATH`.

### 3. Хранилище и RPC (фрагменты, общие контуры)

| Путь | Назначение |
|------|------------|
| `code_analysis/core/database/cst.py` | БД для `cst_trees` |
| `code_analysis/core/database_driver_pkg/rpc_handlers_cst_modify.py` | RPC: модификация CST |
| `code_analysis/core/database_driver_pkg/rpc_handlers_ast_cst_query.py` | RPC: запросы AST/CST по файлу |
| `code_analysis/core/database_driver_pkg/rpc_handlers_ast_modify.py` | RPC: модификация через дерево |
| `code_analysis/core/database_client/objects/ast_cst.py` | Модели узлов для протокола клиента |
| `code_analysis/core/database_client/objects/xpath_filter.py` | Фильтры/XPath |
| `code_analysis/core/database_client/objects/tree_action.py` | Действия над деревом в RPC |

Эти файлы **тяжело отрывают** от остального `code_analysis` — в снимке для справки и точечного переноса.

### 4. Интеграция с обработчиком файлов

| Путь | Назначение |
|------|------------|
| `code_analysis/core/file_handlers/python_handler.py` | Запись Python через CST replace-ops и связь с `cst_tree` |

### 5. CLI (compose)

| Путь | Назначение |
|------|------------|
| `code_analysis/cli/cst_compose_*.py` | Вспомогательные скрипты compose |

Полный перечень путей: **`FILE_LIST.txt`** в корне `cst-code/`.

---

## Рекомендуемая модель продуктовой политики

1. **Просмотр и анализ** — AST из БД и/или свежий `ast.parse`, декларативный outline с `stable_id` / сущностями где есть.
2. **Редактирование** — только CST-сессия (`cst_load_file` → мутации → `cst_save_tree` или ваш пайплайн).
3. После записи — **обновление AST** в индексе, чтобы слой чтения не расходился с диском.

---

## Зависимости

- **Python** ≥ 3.10 (как у основного проекта)
- **`libcst`** ≥ 1.1 — для CST
- Для AST-команд и БД — пакеты из корневого `pyproject.toml` (`mcp-proxy-adapter`, драйвер БД и т.д.); точный список — по `import` в нужных модулях.

---

## Как использовать

### В том же репозитории

Python по умолчанию импортирует из **`code_analysis/`** в корне проекта, **не** из `cst-code/`. Каталог `cst-code/` — **дубликат для ревизии и выноса**.

### Перенос в новый проект

1. CST-ядро: `core/cst_tree`, `core/cst_module`, `core/mutable_cst`, `cst_query`, `core/exceptions.py` (или выделенные исключения).
2. AST-ядро для сервера: `core/ast_utils.py`, `core/database/ast.py`, при необходимости — команды из `commands/ast/` после выделения `BaseMCPCommand` и доступа к БД.
3. Поднять **`libcst`**, прогнать тесты на новом пакете.
4. Команды MCP переносить **после** определения `project_id`, диска и политики бэкапов.

Ориентиры CST: `tree_builder.load_file_to_tree`, `tree_modifier.modify_tree`, `tree_saver.save_tree_to_file`, `cst_query.query_source`, `cst_module.apply_replace_ops`.

### Регистрация в текущем сервере

CST — `code_analysis/hooks_register_part1.py` (блок CST и `cst_apply_buffer`). Команды AST регистрируются отдельно (см. основной `hooks` / registration).

---

## Ограничения снимка

- Не все транзитивные зависимости (очереди, полный драйвер БД, `update_indexes_*`) включены — только модули, **смыслово относящиеся к CST/AST и перечисленным командам**.
- Дублирование с **`code_analysis/`**: при изменениях в основном коде копию в `cst-code/` обновляют вручную или скриптом.

---

## Автор

Исходный код — проект **code-analysis** (Vasiliy Zdanovskiy). Снимок — вспомогательный артефакт для выделения CST и сопутствующего AST-слоя в отдельный продукт или репозиторий.
