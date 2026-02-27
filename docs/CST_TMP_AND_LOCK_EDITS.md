# CST .tmp and file lock — step-by-step code edits

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

One code file per step. Order matters where one step depends on another.

**Execution:** Plan applied. Step 1 and Step 2 were already implemented in code; verified and lint (black, flake8) passed.

---

## Step 1: `code_analysis/commands/cst_load_file_command.py`

**Goal:** Align load with the .tmp convention (no registry), add file lock, fix missing write.

1. **Delete existing .tmp at start of read**  
   After resolving `target` and before any `load_file_to_tree` / copy:
   - `path_tmp = Path(str(target) + ".tmp")`
   - If `path_tmp.exists()`: `path_tmp.unlink()` (and optionally `path_tmp.with_suffix(path_tmp.suffix + ".lock")` if you use a separate lock file next to .tmp; if lock is `path.lock`, deleting .tmp is enough for the load side).

2. **Wrap the whole load block in a file lock**  
   Import `file_lock` from `..core.file_lock`.  
   After the `database.disconnect()` and before `tree = None` / `path_tmp = None`:
   - Open a `with file_lock(target):` block that contains all of:
     - the `try: load_file_to_tree(str(target))` / `except cst.ParserSyntaxError:` branch,
     - building `commented_lines_info`,
     - `load_file_to_tree(str(path_tmp))` when used,
     - the parent-node resolution loop,
     - and the construction of `data` / `return SuccessResult(data=data)`.
   So the entire “read target or target.tmp and build tree” runs under one lock on `target`.

3. **Remove the registry call**  
   Delete the line:
   - `register_temp_file_for_tree(tree.tree_id, path_tmp)`  
   (No replacement; registry is no longer used.)

4. **Ensure .tmp is written once after the fix loop**  
   In the `except cst.ParserSyntaxError:` branch, after the `for _ in range(_MAX_SYNTAX_FIX_ITERATIONS):` loop:
   - The loop updates `lines` in memory and currently does `path_tmp.write_text(...)` inside the loop. When the loop exits by `break` (parse succeeded), the last successful parse used the current `lines` in memory; that same content must be on disk for `load_file_to_tree(str(path_tmp))`.
   - Add a single write **after** the loop, before `load_file_to_tree(str(path_tmp))`:
     - `path_tmp.write_text("\n".join(lines), encoding="utf-8")`
   - So: after the `else: raise ValueError(...)`, add this write, then call `load_file_to_tree(str(path_tmp), ...)`.
   - Optionally remove the `path_tmp.write_text` from inside the loop (so .tmp is written only once at the end); either way, the final content on disk must match the final `lines` before `load_file_to_tree`.

5. **Optional response field**  
   You can keep `data["temp_file"] = str(path_tmp) if path_tmp else None` for debugging; it does not affect the .tmp convention.

**Result:** Load always clears a stale `.tmp` for that file, works only on `.tmp` when there is a syntax error, holds a lock for the whole read, and never registers the temp path. No backup on read.

---

## Step 2: `code_analysis/core/cst_tree/tree_saver.py`

**Goal:** Save via `target.tmp` and hold a file lock for the duration of the save.

1. **Import file lock**  
   At top level:
   - `from ..file_lock import file_lock`  
   (or from `code_analysis.core.file_lock` if relative from `tree_saver` is `..` for `core`.)

2. **Use a fixed .tmp path instead of mkstemp**  
   Replace the block that uses `tempfile.mkstemp(..., suffix=".py", prefix="cst_save_", dir=target_path.parent)` and then writes source into that path:
   - Define `temp_file = Path(str(target_path) + ".tmp")`.
   - Write the generated `source_code` into `temp_file` (same directory as `target_path`), e.g. `temp_file.write_text(source_code, encoding="utf-8")`.
   - Remove the use of `temp_fd` / `mkstemp` and the subsequent `os.fdopen` / `close`; use only `temp_file` as the path to the temporary content.

3. **Keep validation on the temp content**  
   After writing to `temp_file`, keep the existing validation step (e.g. `compile(source_code, ...)`) so that you still validate before replacing the original.

4. **Wrap the whole save in a file lock**  
   After resolving `target_path` and ensuring the parent directory exists, wrap the rest of the save logic in:
   - `with file_lock(target_path):`
   So that inside the lock you:
   - (Optional) validate original if desired.
   - Create backup of `target_path` if it exists (BackupManager / versioning or git as per project).
   - Write to `temp_file` (target_path + ".tmp").
   - Validate the generated code.
   - Begin DB transaction.
   - `os.replace(str(temp_file), str(target_path))` (this replaces the original with .tmp and removes .tmp).
   - Update database, commit, git if used, etc.
   - In `finally`, do not try to delete `temp_file` after a successful `os.replace` (it is already gone).

5. **Cleanup on failure**  
   In the `except`/`finally` path, if you created `temp_file` but did not call `os.replace`, delete `temp_file` if it exists (e.g. `temp_file.unlink(missing_ok=True)`) so that the next read can start from a clean “no .tmp” state.

**Result:** Save writes only to `target.tmp`, then replaces the original with it under a lock; backup/versioning happens before replace. No registry; .tmp is defined solely by the path convention.

---

## Summary

| Step | File | Main change |
|------|------|-------------|
| 1 | `cst_load_file_command.py` | Remove .tmp at start; lock for read; remove registry call; ensure one write of .tmp after fix loop. |
| 2 | `tree_saver.py` | Use `target + ".tmp"` instead of mkstemp; wrap save in `file_lock(target_path)`; cleanup .tmp on failure. |

After both steps: one file of code per step, .tmp used consistently for read (error path) and write, and file locking prevents other processes/threads from opening the file during read or write.
