#!/command/with-contenv bash
# Oneshot (root), idempotent -- runs every boot. Stays root: this is only a
# TCP/SQL client to Postgres, it writes no files into casuser-owned dirs.
# Applies
# POSTGRES_SUPERUSER_PASSWORD and ensures the code_analysis role/database
# exist, against 127.0.0.1:5432 (config.json's driver.config.host must be
# 127.0.0.1 in this all-in-one image -- a later phase owns the config template).
set -euo pipefail

if [[ ! -f /etc/casmgr/config.json ]]; then
    echo "ERROR: config not mounted at /etc/casmgr/config.json" >&2
    exit 1
fi
if [[ ! -f /var/casmgr/secrets/.env ]]; then
    echo "ERROR: /var/casmgr/secrets/.env not found." >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
source /var/casmgr/secrets/.env
set +a

: "${POSTGRES_SUPERUSER_PASSWORD:?POSTGRES_SUPERUSER_PASSWORD not set in /var/casmgr/secrets/.env}"
: "${CODE_ANALYSIS_POSTGRES_PASSWORD:?CODE_ANALYSIS_POSTGRES_PASSWORD not set in /var/casmgr/secrets/.env}"

# set-superuser-password needs the *current* connect password too; on this
# cluster they are always the same value (set via --pwfile in 10-pg-initdb,
# or by a prior run of this same idempotent step), so the ALTER ROLE is a
# harmless no-op past the first boot.
export POSTGRES_SUPERUSER_CONNECT_PASSWORD="${POSTGRES_SUPERUSER_PASSWORD}"

/opt/casmgr/venv/bin/python /opt/casmgr/scripts/postgres_setup_from_env_config.py \
    --config /etc/casmgr/config.json set-superuser-password

/opt/casmgr/venv/bin/python /opt/casmgr/scripts/postgres_setup_from_env_config.py \
    --config /etc/casmgr/config.json ensure-app-db

echo "30-pg-init: superuser password applied, code_analysis role/db ensured."
