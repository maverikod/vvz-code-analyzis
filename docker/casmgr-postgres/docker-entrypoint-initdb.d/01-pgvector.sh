#!/bin/bash
# Ensure pgvector is available on first cluster init (image already includes extension files).
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL
