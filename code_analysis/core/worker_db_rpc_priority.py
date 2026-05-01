"""Shared RPC request priority for background DB work (Postgres pool lanes / metrics).

Indexer and vectorizer use the same non-zero priority so pool routing and
observability stay consistent across packages.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

BACKGROUND_WORKER_DB_RPC_PRIORITY = 1
