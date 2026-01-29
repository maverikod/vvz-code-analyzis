# Database Restore Command

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

**File:** `commands/database_restore_mcp_commands.py`.

## restore_database

Restore (rebuild) SQLite database by sequentially indexing directories from config. Reads list of project roots from config, creates/clears DB, runs full indexing for each root. Used for disaster recovery or initial bulk setup.
