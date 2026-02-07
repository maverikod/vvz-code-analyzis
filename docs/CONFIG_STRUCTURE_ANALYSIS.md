# Configuration structure analysis

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

This document describes the code-analysis-server configuration: allowed keys (only what is used in code), generator CLI arguments, validation coverage, and alignment between generator, validator, and runtime (ServerConfig).

---

## 1. Principles

1. **Config contains only what is used in code.** The `code_analysis` section may contain only keys defined in `ServerConfig` (see `code_analysis/core/config.py`) or the special key `database` (used by the database driver, not by ServerConfig). The validator rejects any other key in `code_analysis` with an error.
2. **Generator output matches CLI arguments.** Every CLI option for the `generate` command corresponds to a config field; the generated file reflects the provided args or defaults.
3. **CLI allows setting any available parameter.** All code_analysis parameters that the generator can write can be set via CLI (see Section 5).
4. **Validator matches code and generator.** The validator checks types and value ranges for every allowed key and nested structure (including `file_watcher`, `worker`, `indexing_worker`, `database.driver`, `chunker`, `embedding`).

---

## 2. Top-level sections

The config file (e.g. `config.json`) is a single JSON object. Only the **code_analysis** section is specific to this project; the rest (server, client, registration, queue_manager, etc.) come from mcp-proxy-adapter and are generated/validated by the base layer.

| Section          | Used by                | Purpose |
|------------------|------------------------|---------|
| server           | mcp-proxy-adapter      | Host, port, protocol, SSL, log_dir |
| queue_manager    | mcp-proxy-adapter      | Job queue (enabled, in_memory, etc.) |
| **code_analysis**| code_analysis only    | DB, workers, FAISS, services (see below) |
| …                | mcp-proxy-adapter      | registration, auth, transport, etc. |

---

## 3. Allowed code_analysis keys (canonical list)

Allowed keys = **ServerConfig.model_fields** ∪ **{"database"}**. No other keys are permitted; the validator reports an error for unknown keys.

| Key                         | Type    | Used in code | Validator | Generator CLI |
|----------------------------|---------|--------------|-----------|----------------|
| host                       | str     | yes          | type      | server_host    |
| port                       | int     | yes          | type+range| server_port    |
| log                        | str     | yes          | type      | --code-analysis-log |
| db_path                    | str     | yes          | type      | --code-analysis-db-path |
| dirs                       | list    | yes          | —         | (not in CLI)   |
| chunker                    | object  | yes          | type      | (not in CLI)   |
| embedding                  | object  | yes          | type      | (not in CLI)   |
| faiss_index_path           | str     | yes          | type      | --code-analysis-faiss-index-path |
| vector_dim                 | int     | yes          | type      | --code-analysis-vector-dim |
| min_chunk_length           | int     | yes          | type      | --code-analysis-min-chunk-length |
| vectorization_retry_attempts| int     | yes          | type      | --code-analysis-retry-attempts |
| vectorization_retry_delay  | float   | yes          | type      | --code-analysis-retry-delay |
| **database**               | object  | driver only  | driver    | --code-analysis-driver-type, --code-analysis-driver-path |
| worker                     | object  | yes          | type+ranges | (not in CLI) |
| file_watcher               | object  | yes          | type+ranges | --file-watcher-* |
| indexing_worker            | object  | yes          | type+ranges | --indexing-worker-* |

- **database** is not a field of ServerConfig; it is read only by the database driver startup. All other keys are ServerConfig fields.

---

## 4. code_analysis subsections

### 4.1 database (driver only)

- **database.driver.type**: string (`sqlite`, `sqlite_proxy`, `postgres`, `mysql`).
- **database.driver.config**: object with `path` (DB file); for `sqlite_proxy` also `worker_config` (command_timeout, poll_interval).

Generator creates this from `--code-analysis-driver-type` and `--code-analysis-driver-path`. Validator validates type and config; runtime uses it only in driver startup.

### 4.2 worker (vectorization)

Used by vectorization worker and by file watcher (watch_dirs). Shape: enabled, poll_interval, batch_size, retry_attempts, retry_delay, watch_dirs, dynamic_watch_file, log_path, log_rotation, circuit_breaker, batch_processor. Generator does not add this block (no CLI for it yet). Validator validates types and value ranges (poll_interval ≥ 1, batch_size ≥ 1, circuit_breaker, batch_processor).

### 4.3 file_watcher

Shape: enabled, scan_interval, log_path, version_dir, max_scan_duration, ignore_patterns, log_rotation. Generator adds a default block and applies `--file-watcher-enabled`, `--file-watcher-disabled`, `--file-watcher-scan-interval`, `--file-watcher-log-path`, `--file-watcher-version-dir`. Validator validates types and value ranges (scan_interval ≥ 0, max_scan_duration ≥ 0).

### 4.4 indexing_worker

Shape: enabled, poll_interval, batch_size, log_path. Generator adds this and applies `--indexing-worker-enabled`, `--indexing-worker-disabled`, `--indexing-worker-poll-interval`, `--indexing-worker-batch-size`, `--indexing-worker-log-path`. Validator validates types and value ranges (poll_interval ≥ 1, batch_size ≥ 1).

---

## 5. Generator CLI → config mapping

All code_analysis parameters that the generator writes can be set via CLI. Base (mcp-proxy-adapter) server/registration/queue args are not listed here.

| CLI argument | Config path | Default |
|--------------|-------------|---------|
| --code-analysis-db-path | code_analysis.db_path | data/code_analysis.db |
| --code-analysis-driver-type | code_analysis.database.driver.type | sqlite_proxy |
| --code-analysis-driver-path | code_analysis.database.driver.config.path | same as db_path |
| --code-analysis-log | code_analysis.log | logs/code_analysis.log |
| --code-analysis-faiss-index-path | code_analysis.faiss_index_path | data/faiss_index.bin |
| --code-analysis-vector-dim | code_analysis.vector_dim | 384 |
| --code-analysis-min-chunk-length | code_analysis.min_chunk_length | 30 |
| --code-analysis-retry-attempts | code_analysis.vectorization_retry_attempts | 3 |
| --code-analysis-retry-delay | code_analysis.vectorization_retry_delay | 1.0 |
| --indexing-worker-enabled / --indexing-worker-disabled | code_analysis.indexing_worker.enabled | True |
| --indexing-worker-poll-interval | code_analysis.indexing_worker.poll_interval | 30 |
| --indexing-worker-batch-size | code_analysis.indexing_worker.batch_size | 5 |
| --indexing-worker-log-path | code_analysis.indexing_worker.log_path | logs/indexing_worker.log |
| --file-watcher-enabled / --file-watcher-disabled | code_analysis.file_watcher.enabled | True |
| --file-watcher-scan-interval | code_analysis.file_watcher.scan_interval | 60 |
| --file-watcher-log-path | code_analysis.file_watcher.log_path | logs/file_watcher.log |
| --file-watcher-version-dir | code_analysis.file_watcher.version_dir | data/versions |

Server host/port for the **server** section are set by `--server-host` and `--server-port`; the generator also uses them for `code_analysis.host` and `code_analysis.port` when building the code_analysis block.

---

## 6. Validator coverage

- **Allowed keys**: Errors on any `code_analysis` key not in `ALLOWED_CODE_ANALYSIS_KEYS` (ServerConfig.model_fields ∪ {"database"}).
- **Types**: All top-level and nested fields listed in Section 3 and 4 are type-checked when present (including file_watcher, chunker, embedding, database.driver, worker, indexing_worker).
- **Value ranges**: Ports 1–65535; worker poll_interval and batch_size ≥ 1; indexing_worker poll_interval and batch_size ≥ 1; file_watcher scan_interval and max_scan_duration ≥ 0; circuit_breaker and batch_processor constraints as in code.
- **Database driver**: type required, config required, path required for sqlite/sqlite_proxy, worker_config numeric checks for sqlite_proxy.
- **File existence**: SSL/cert files and database path parent directory checks where applicable.

---

## 7. Runtime (main.py)

- Loads full config; reads `code_analysis` section.
- Builds ServerConfig only from allowed keys: `server_config_dict = { k: v for k, v in code_analysis_config.items() if k in ServerConfig.model_fields }`. So `database` is never passed to ServerConfig (used separately for driver startup).
- Workers (vectorization, file_watcher, indexing) read their options from ServerConfig (worker, file_watcher, indexing_worker) or from driver config (database.driver).

---

## 8. Summary

| Requirement | Implementation |
|-------------|----------------|
| Config contains only what is used | Allowed keys = ServerConfig.model_fields + "database"; validator errors on unknown keys. |
| Generator output matches CLI args | All code_analysis fields written by generator can be set via CLI; generated file reflects args or defaults. |
| CLI allows any available parameter | All code_analysis generator parameters have corresponding CLI options (Section 5). |
| Validator matches code and generator | Validator checks all allowed keys and nested structures (types + value ranges), including file_watcher. |
