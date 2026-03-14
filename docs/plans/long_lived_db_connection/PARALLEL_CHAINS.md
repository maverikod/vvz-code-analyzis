# Parallel Chains: Long-Lived DB Connection

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [PLAN.md](PLAN.md)  
**TZ:** [TZ.md](TZ.md)

---

## Сколько шагов и где они

Всего **9 шагов** — ровно **9 файлов** в каталоге `steps/` (step_01 … step_09):

- **Шаги 01–04** — последовательная цепочка (см. ниже).
- **Шаги 05–09** — параллельная цепочка после Step 03: по одному файлу на команду (delete_project, list_watch_dirs, permanently_delete_from_trash, clear_trash, restore_project_from_trash). Файлы: `step_05_...md` … `step_09_...md`.

**Шаги 10, 11, …** — это не «больше 10 шагов», а возможные **номера** следующих шагов. Файлов `step_10_*.md`, `step_11_*.md` и т.д. в `steps/` **нет**: план ограничен 9 шагами; остальные команды уже получают БД через `BaseMCPCommand._open_database_from_config()` (т.е. через shared), поэтому отдельные step-файлы для них не заводились.

---

## Что уже реализовано в коде (на момент актуализации документа)

- **01** — модуль `code_analysis/core/shared_database.py` (set/get/close, proxy).
- **02** — в `main_app_events.py`: открытие БД и `set_shared_database()` до приёма запросов, при остановке `close_shared_database()` до остановки воркеров.
- **03** — в `base_mcp_command.py`: `_open_database_from_config` / `_open_database` вызывают `get_shared_database()`.
- **04** — в `base_mcp_command_open_db.py`: `open_database_from_config_impl()` используется при старте; хелперы целостности и схемы сохранены.
- **05–09** — команды delete_project, list_watch_dirs, permanently_delete_from_trash, clear_trash, restore_project_from_trash используют `self._open_database_from_config()` (shared), без прямого `DatabaseClient()` + connect.

То есть шаги 01–09 в коде **дописаны**. Шаги с номерами 10+ не создавались (файлов нет, в них не было необходимости).

---

## Sequential chain (must run in order)

1. **Step 01** — Create `shared_database` module (holder + get/set/close; optional proxy with no-op disconnect).
2. **Step 02** — Startup/shutdown: open long-lived connection after driver start, set in holder; on shutdown close connection then stop workers. Depends on Step 01 (holder API).
3. **Step 03** — BaseMCPCommand: `_open_database_from_config` / `_open_database` use `get_shared_database()`. Depends on Step 01 (and ideally 02 so shared is set at startup).
4. **Step 04** — Extract “open + probe once” from `base_mcp_command_open_db` for use by startup; keep integrity and schema helpers. Can be parallel with 03 if the “open once” function does not depend on shared_database; otherwise after 01.

---

## Parallel chain (after Step 03 is done)

Steps **05, 06, 07, 08, 09** — по одному шагу на команду. Файлы в `steps/`: `step_05_delete_project_use_shared.md`, `step_06_list_watch_dirs_use_shared.md`, `step_07_permanently_delete_from_trash_use_shared.md`, `step_08_clear_trash_use_shared.md`, `step_09_restore_project_from_trash_use_shared.md`. Шаги независимы друг от друга (каждый меняет только свой файл команды) и могут выполняться **параллельно** разными исполнителями после завершения Step 03.

---

## Dependency summary

- **01 → 02 → 03** (strict order).
- **04** can run after 01; can be parallel with 02 or 03 if “open once” is a pure function that does not call `get_shared_database`.
- **05–09** depend only on 03; parallel with each other.
- **Step 10, 11, …** (remaining command files, not yet created): after 03 and preferably after 05–09; can be split into multiple parallel steps (one file per step).
