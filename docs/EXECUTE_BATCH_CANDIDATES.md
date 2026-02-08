# Database execute/execute_batch usage and batching candidates

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Summary

- **Все вызовы** `db.execute()` / `database.execute()` и `execute_batch()` в проекте (кроме низкоуровневого драйвера и RPC handler’ов).
- **Кандидаты на объединение в батч** — участки с несколькими подряд идущими независимыми запросами (SELECT или DML), которые можно заменить одним вызовом `execute_batch(operations)` и разбором `results[i]`.

---

## 1. Высокий приоритет (много RPC подряд, критичный путь)

### 1.1 GetDatabaseStatus — MCP и CLI

| Файл | Строки | Запросы | Рекомендация |
|------|--------|---------|--------------|
| `commands/worker_status_mcp_commands.py` | 529–873+ | 20+ последовательных `db.execute(SELECT ...)` | **Объединить в один execute_batch**: все SELECT’ы независимы, порядок фиксирован; один RPC вместо 20+. Устраняет таймаут/падение при получении метрик. |
| `commands/worker_status.py` | 392–517+ | Аналогично ~15+ `db.execute(SELECT ...)` для статуса БД | **Объединить в execute_batch** по тому же шаблону, что и MCP (или общий хелпер). |

Запросы в get_database_status (по порядку):

- SELECT COUNT(*) FROM projects  
- SELECT (projects + subqueries) LIMIT 10  
- SELECT COUNT(*) FROM files (и варианты: deleted, has_docstring, needing_chunking, with_chunks, indexed, needing_indexing)  
- SELECT COUNT(*) FROM code_chunks (total, vectorized, not_vectorized)  
- SELECT COUNT(*) files/chunks updated in last 24h  
- SELECT worker_stats (если через execute)  
- SELECT samples: needing_indexing_sample, needing_chunking_sample, needing_vectorization_sample  

Все без зависимости по данным между шагами — только индексы в `results[i]` при разборе.

---

### 1.2 check_vectors_command

| Файл | Строки | Запросы | Рекомендация |
|------|--------|---------|--------------|
| `commands/check_vectors_command.py` | 361–422 | 6–8 последовательных `db.execute(SELECT ...)` в одной ветке (total, with vector_id, with embedding_model, without vector_id, sample) | **Объединить в execute_batch**: два набора — с `project_id=?` и без; каждый набор — один батч, разбор по индексам. |

---

## 2. Средний приоритет (несколько RPC подряд)

### 2.1 clear_project_data_impl

| Файл | Строки | Запросы | Рекомендация |
|------|--------|---------|--------------|
| `commands/clear_project_data_impl.py` | 178–235 | `classes = database.execute(SELECT id FROM classes...)`, `content_rows = database.execute(SELECT id FROM code_content...)`, затем два `database.execute(DELETE ...)` для duplicates, затем уже `execute_batch(delete_ops)` | **Батчить**: (1) два SELECT (classes, content) — один execute_batch из двух операций; (2) два DELETE по duplicates можно добавить в общий батч или отдельный execute_batch из 2 операций. Транзакция уже есть. |

---

### 2.2 project_management_mcp_commands (change_project_id)

| Файл | Строки | Запросы | Рекомендация |
|------|--------|---------|--------------|
| `commands/project_management_mcp_commands.py` | 598–683 | Несколько веток с одиночными `database.execute(UPDATE projects...)` или `INSERT INTO projects` в зависимости от условий | Батч не подходит: в каждой ветке один запрос, логика разная (update vs insert, разные поля). Оставить как есть. |

---

### 2.3 AST / code_mapper команды (несколько SELECT подряд)

| Файл | Строки | Запросы | Рекомендация |
|------|--------|---------|--------------|
| `commands/ast/entity_dependencies.py` | 33, 64, 108, 118, 129, 140, 177 | Несколько `db.execute(...)` в одной функции | Часть запросов может быть независимой — можно сгруппировать в один execute_batch и разобрать по индексам (нужен разбор по коду). |
| `commands/ast/statistics.py` | 62, 78, 84 | 3 последовательных SELECT | **Кандидат**: один execute_batch из 3 операций. |
| `commands/ast/list_entities.py` | 86, 104, 122 | 3 вызова с разными параметрами | Если параметры известны до цикла — батч из 3; иначе оставить. |
| `commands/ast/imports.py` | 98, 109, 146 | 2–3 вызова | Аналогично: при возможности собрать список (sql, params) — батч. |
| `commands/ast/dependencies.py` | 100, 133, 179 | import_query, inheritance_query, usage_query | **Кандидат**: один execute_batch из 3 SELECT’ов, разбор results[0..2]. |
| `commands/ast/usages.py` | 110, 151, 211 | 3 вызова | То же: батч из 3 операций. |
| `commands/ast/graph.py` | 114, 157, 202 | 3 вызова | То же: батч из 3. |
| `commands/ast/get_ast.py` | 81, 92 | 2 вызова | Батч из 2. |

---

### 2.4 file_watcher_pkg

| Файл | Строки | Запросы | Рекомендация |
|------|--------|---------|--------------|
| `core/file_watcher_pkg/processor.py` | 463, 472, 568, 595, 615, 623, 665, 679, 723 | Много одиночных execute в разных ветках и циклах | Часть пар (например два подряд SELECT/UPDATE в одном контексте) можно объединять в execute_batch; нужен разбор по контексту (зависимости от предыдущего результата). |
| `core/file_watcher_pkg/multi_project_worker.py` | 372, 382, 438, 466, 596, 611, 631, 672, 831, 847, 902, 913, 936, 951, 976, 989, 1002 | Много execute в циклах и условиях | Аналогично: искать последовательности независимых запросов в одном блоке и батчить их. |

---

### 2.5 indexing_worker_pkg/processing.py

| Файл | Строки | Запросы | Рекомендация |
|------|--------|---------|--------------|
| `core/indexing_worker_pkg/processing.py` | 82, 147, 155, 173, 186, 217, 241, 273, 290, 316, 327, 373 | execute в цикле (по проектам/файлам) и для статистики | Статистику (например несколько COUNT/INSERT подряд в начале/конце цикла) можно батчить; внутренние execute по файлам часто зависят от предыдущего результата — батчить только там, где запросы независимы. |

---

### 2.6 vectorization_worker_pkg

| Файл | Строки | Запросы | Рекомендация |
|------|--------|---------|--------------|
| `core/vectorization_worker_pkg/processing.py` | 172, 182, 193, 203, 223, 245, 352, 413, 534, 638 | Смесь: один тяжёлый SELECT по чанкам и несколько вспомогательных | Там, где подряд идут независимые SELECT (например счётчики), можно объединить в один execute_batch. |
| `core/vectorization_worker_pkg/batch_processor.py` | 58, 158, 308, 420 | Один большой SELECT, потом в цикле единичные execute, в конце уже execute_batch(update_ops) | UPDATE’ы уже в батче. Оставшиеся одиночные execute в цикле зависят от данных — батчить только если появятся блоки независимых запросов. |

---

## 3. Уже используют execute_batch (без изменений или точечно)

| Файл | Использование |
|------|----------------|
| `core/vectorization_worker_pkg/batch_processor.py` | `database.execute_batch(update_ops)` для UPDATE code_chunks (vector_id, embedding_model). |
| `commands/clear_project_data_impl.py` | `database.execute_batch(delete_ops)` для каскадных DELETE; можно дополнительно батчить два SELECT (classes, content) и два DELETE duplicates (см. выше). |
| `commands/cst_compose_module_command.py` | `execute_batch(backup_ops)`, `execute_batch(methods_results)`, `execute_batch(select_ops, transaction_id)`, `execute_batch(delete_ops, transaction_id)`. Остальные одиночные execute (280, 300, 325, …) — кандидаты на объединение в батчи, если они идут подряд и независимы. |

---

## 4. Одиночные вызовы (батч не нужен или неочевиден)

- **project_creation.py** — один SELECT (watch_dir_paths), затем begin → один execute(INSERT) → commit. Батч не даёт выигрыша.
- **base_mcp_command.py** — единичные execute для _get_project_id, config и т.д.
- **client_api_files.py** — много вызовов execute, но с разной логикой и зависимостями; батчить только явные последовательности независимых запросов (по месту).
- **rpc_handlers_index_file.py**, **rpc_handlers_base.py** — низкий уровень (драйвер/RPC), батч уже реализован в handle_execute_batch.
- **database_driver_pkg/drivers/sqlite.py** — прямой вызов cursor.execute; батч на уровне клиента (execute_batch RPC).

---

## 5. Рекомендуемый порядок внедрения

1. **worker_status_mcp_commands.py (get_database_status)** — собрать все SELECT’ы в один список операций, один `db.execute_batch(operations)`, разобрать `results[0]`, `results[1]`, … по текущей логике. Это снимает основную проблему таймаута/падения при получении метрик.
2. **worker_status.py** — тот же набор запросов через общий хелпер или дублирование схемы батча.
3. **check_vectors_command.py** — один или два execute_batch (с project_id и без) вместо 6–8 одиночных execute.
4. **commands/ast/** — по файлам (statistics, dependencies, usages, graph, list_entities, get_ast) объединить последовательные независимые SELECT’ы в execute_batch.
5. **clear_project_data_impl.py** — батч для двух SELECT (classes, content) и при желании для двух DELETE (duplicates).
6. **file_watcher_pkg**, **indexing_worker_pkg**, **vectorization_worker_pkg** — выборочно батчить только явные последовательности независимых запросов после разбора зависимостей.

---

## 6. Общие правила для батча

- Запросы в одном батче **не должны зависеть** от результатов друг друга (или зависимость должна быть через отдельный предварительный батч).
- **Порядок** операций в списке должен совпадать с порядком разбора: `results[i]` соответствует `operations[i]`.
- Для SELECT: `results[i].get("data", [])` — список строк.
- Транзакция: при необходимости вызывать `execute_batch(operations, transaction_id=tid)` с уже открытой транзакцией (как в clear_project_data_impl и cst_compose_module).

---

## 7. Index analysis for SELECTs (schema coverage)

Analysis of SELECT patterns (WHERE, JOIN, ORDER BY) vs existing and added indexes. Schema and indexes are defined in `code_analysis/core/database/base.py`.

### 7.1 files

| Usage in SELECTs | Existing index | Added / note |
|------------------|----------------|--------------|
| `project_id = ?` | `idx_files_project` (project_id) | — |
| `path = ? AND project_id = ?` | UNIQUE(project_id, path) → implicit index | — |
| `deleted = 1` | `idx_files_deleted` (deleted) WHERE deleted = 1 | — |
| `has_docstring = 1` | — | Not added: single COUNT, low impact. |
| `(deleted = 0 OR deleted IS NULL) AND needs_chunking = 1` | — | **Added:** `idx_files_needs_indexing` ON files(project_id, updated_at) WHERE (deleted = 0 OR deleted IS NULL) AND needs_chunking = 1 — supports COUNT and “ORDER BY updated_at ASC LIMIT ?” in indexing worker. |
| `updated_at > ...`, `ORDER BY updated_at` | — | **Added:** `idx_files_updated_at` ON files(updated_at) — for “recent activity” and sample ordering. |

### 7.2 code_chunks

| Usage in SELECTs | Existing index | Added / note |
|------------------|----------------|--------------|
| `project_id = ?` | `idx_code_chunks_project` | — |
| `file_id IN (...)` / `file_id = ?` | `idx_code_chunks_file` | — |
| `vector_id IS NULL` / `IS NOT NULL` | `idx_code_chunks_vector`, `idx_code_chunks_not_vectorized` (project_id, id) WHERE vector_id IS NULL | — |
| `embedding_model IS NOT NULL AND project_id = ?` | — | **Added:** `idx_code_chunks_project_embedding_model` ON code_chunks(project_id) WHERE embedding_model IS NOT NULL — for check_vectors_command. |
| `created_at > ...` | — | **Added:** `idx_code_chunks_created_at` ON code_chunks(created_at) — for “chunks updated in last 24h”. |

### 7.3 projects, classes, usages, ast_trees, code_content, code_duplicates

| Table | Usage | Index |
|-------|--------|--------|
| projects | id, root_path, watch_dir_id, ORDER BY name | idx_projects_root_path, idx_projects_watch_dir_id; PRIMARY KEY(id). |
| classes | file_id IN (...), name, bases LIKE | idx_classes_file, idx_classes_name. bases LIKE '%...' cannot use index. |
| usages | file_id, target_type+target_name, target_class+target_name | idx_usages_file, idx_usages_target, idx_usages_class_name. |
| ast_trees | file_id, project_id, ast_hash | idx_ast_trees_file, idx_ast_trees_project, idx_ast_trees_hash. |
| code_content | file_id IN (...) | idx_code_content_file. |
| code_duplicates | project_id | idx_code_duplicates_project. |
| duplicate_occurrences | duplicate_id IN (SELECT id FROM code_duplicates WHERE project_id = ?) | idx_duplicate_occurrences_duplicate. |

### 7.4 Indexes added in schema (base.py)

The following indexes were added so that the main SELECT patterns are covered:

- **idx_code_chunks_created_at** — `code_chunks(created_at)` for recent-activity and time-based filters.
- **idx_code_chunks_project_embedding_model** — `code_chunks(project_id) WHERE embedding_model IS NOT NULL` for check_vectors “chunks with embedding_model” per project.
- **idx_files_updated_at** — `files(updated_at)` for “files updated in last 24h” and ORDER BY updated_at.
- **idx_files_needs_indexing** — `files(project_id, updated_at) WHERE (deleted = 0 OR deleted IS NULL) AND needs_chunking = 1` for “files needing indexing” count and indexing worker “ORDER BY updated_at ASC LIMIT ?”.

No index was added for:

- `files.has_docstring = 1` (single global COUNT).
- `classes.bases LIKE '%...'` / `imports.module LIKE '%...'` (leading wildcard; index not useful).

---

## 8. What to change (concrete steps)

For each candidate, this section states **what to change** in code. When source tables are large, the preferred approach is to **select by filter into a temporary table** and run the batch (or subsequent queries) against that temp table so the main tables are scanned once and the rest of the work is on a small dataset.

### 8.1 GetDatabaseStatus (worker_status_mcp_commands.py, worker_status.py)

**Change:**

1. **Always:** Build a single list of operations: each element `(sql, params)` for every SELECT in the current order (projects COUNT, projects with stats LIMIT 10, files COUNT, files WHERE deleted=1, … through all file/chunk counts, recent_activity, then the three samples). Call `db.execute_batch(operations)` once. Parse `results[0]`, `results[1]`, … in the same order into the existing result dict (project_count, projects_with_stats, total_files, …).
2. **When tables are large (e.g. millions of rows in `files` / `code_chunks`):** Optionally add a “heavy” path:
   - Create session temp tables in one pass per main table, then run the batch against them.
   - Example for chunks:  
     `CREATE TEMP TABLE _chunk_stats AS SELECT COUNT(*) AS total, SUM(CASE WHEN vector_id IS NOT NULL THEN 1 ELSE 0 END) AS vectorized, SUM(CASE WHEN vector_id IS NULL THEN 1 ELSE 0 END) AS not_vectorized FROM code_chunks`  
     and similarly one temp table for file-level aggregates if needed. Then the batch uses `_chunk_stats` / `_file_stats` instead of scanning the big tables again. Alternatively, replace several COUNT queries with one or two queries using conditional aggregation and keep the rest of the batch for the remaining SELECTs (e.g. samples).  
   - Prefer batching first; introduce temp tables only when profiling shows full-table scans are too slow.

**Result:** One RPC (or one RPC + one small batch against temp tables) instead of 20+ RPCs; lower timeout/crash risk.

---

### 8.2 check_vectors_command.py

**Change:**

1. **Always:** Replace the 6–8 sequential `db.execute(...)` with one `execute_batch(operations)`. Two variants: with `project_id` (all queries use `WHERE project_id = ?`) and without (no filter). Build `operations` as list of `(sql, params)` in fixed order; parse `results[i]` into total_chunks, chunks_with_vector, chunks_with_model, chunks_pending, samples.
2. **When `code_chunks` is large:** Use a temporary table so the big table is read once:
   - If `project_id` is set:  
     `CREATE TEMP TABLE _chunks AS SELECT id, chunk_type, chunk_text, vector_id, embedding_model, source_type FROM code_chunks WHERE project_id = ?`  
     Then run the batch of COUNT/sample queries **against `_chunks`** (same SQL but from `_chunks` instead of `code_chunks`, and params without `project_id`). All stats and the sample come from the small temp table.
   - If no `project_id`, the whole table is scanned anyway; batching alone reduces RPC. Optionally: `CREATE TEMP TABLE _chunks AS SELECT ... FROM code_chunks` then run the batch on `_chunks` (only if one full scan + many small scans on temp is faster than many scans on the main table — measure).

**Result:** Fewer RPCs; with temp table, one scan of `code_chunks` (optionally filtered by project) and all further work on a small temp table.

---

### 8.3 clear_project_data_impl.py

**Change:**

1. **Always:** (1) Batch the two SELECTs: `operations = [(sql_classes, (file_ids,)), (sql_content, (file_ids,))]` (with the same `placeholders` as now), then `database.execute_batch(operations, transaction_id=transaction_id)`, parse `results[0]` → class_ids, `results[1]` → content_ids. (2) Put the two duplicate DELETEs into one `execute_batch` of two operations (same transaction_id).
2. **When `classes` / `code_content` are very large:** Even with `file_id IN (...)`, if the project has many files, the two SELECTs can touch many rows. Option: create temp tables for the filtered subset and use them in deletes:
   - `CREATE TEMP TABLE _class_ids AS SELECT id FROM classes WHERE file_id IN (...)`  
   - `CREATE TEMP TABLE _content_ids AS SELECT id FROM code_content WHERE file_id IN (...)`  
   Then build the existing delete batch to reference these (e.g. `DELETE FROM ... WHERE id IN (SELECT id FROM _class_ids)`) or keep building list of IDs from the temp table with one SELECT from each temp table. Main benefit: one scan of `classes` and one of `code_content` into temp; subsequent deletes can use the temp tables if the driver/schema allow.

**Result:** Fewer RPCs; with temp tables, one scan per main table for the project’s subset.

---

### 8.4 AST commands (statistics, dependencies, usages, graph, list_entities, get_ast)

**Change:**

1. **Always:** Where there are 2–3 consecutive independent SELECTs (e.g. statistics: ast_trees COUNT, files COUNT; dependencies: import_query, inheritance_query, usage_query), replace with one `execute_batch(operations)` and map `results[0]`, `results[1]`, `results[2]` into the existing variables.
2. **When `files` / `ast_trees` / `classes` / `usages` are large:** These commands already filter by `project_id` (or file_id). To avoid repeated scans of large tables:
   - Create a temp table for the project’s files:  
     `CREATE TEMP TABLE _proj_files AS SELECT id, path FROM files WHERE project_id = ? AND (deleted = 0 OR deleted IS NULL)`  
     Then run the 2–3 queries joining with `_proj_files` (e.g. from `ast_trees`, `classes`, `usages` JOIN `_proj_files` on file_id). That way `files` is scanned once; the rest of the work is on a small temp table and indexed lookups.

**Result:** Fewer RPCs; with temp table, one scan of `files` per project and lighter work for the batch.

---

### 8.5 file_watcher_pkg, indexing_worker_pkg, vectorization_worker_pkg

**Change:**

- Identify **consecutive independent** execute calls in the same block (e.g. two SELECTs or two UPDATEs that do not depend on the first result). Replace with `execute_batch([(sql1, p1), (sql2, p2)])` and use `results[0]`, `results[1]`.
- **When source tables are large:** If a block first selects a large set (e.g. all file_ids for a project) and then runs several queries that only need that set, consider:  
  `CREATE TEMP TABLE _ids AS SELECT id FROM files WHERE project_id = ? AND ...`  
  then run the subsequent queries against or joining `_ids`, so the main table is not rescanned.

**Result:** Fewer RPCs; optional temp table to turn one heavy scan into a small working set.

---

## 9. When to use temporary tables (summary)

| Situation | Recommendation |
|-----------|----------------|
| Many small independent SELECTs over **same large table** | Prefer **one temp table** with a filter (e.g. `WHERE project_id = ?`), then run the batch of queries against the temp table. Main table is scanned once. |
| Global stats (no project filter), many COUNTs | **Batch first** to reduce RPC. If the table is huge, consider one or two queries with conditional aggregation, or one `CREATE TEMP TABLE ... AS SELECT` that computes several aggregates in one scan, then run the rest of the batch on that temp table. |
| Already filtered by project/file | Temp table for the **filtered subset** (e.g. `_chunks` for one project, `_proj_files` for one project) so all subsequent queries hit the small temp table. |
| Two SELECTs that share the same filter (e.g. classes and content by file_ids) | Either batch the two SELECTs only, or create two temp tables `_class_ids`, `_content_ids` from the same filter and use them in the delete batch. |
| Single query or dependent chain | No batching; temp table only if the single query can be split into “fill temp once” + “cheap queries on temp”. |

**SQLite:** Use `CREATE TEMP TABLE ...` or `CREATE TEMPORARY TABLE ...`; the table is connection-scoped and dropped when the connection is closed. All execute/execute_batch calls in this project go through the same driver, so temp tables created in one request are visible to subsequent execute_batch calls on the same connection within the same request.
