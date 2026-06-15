#!/usr/bin/env bash
# casmgr-server container entrypoint: secrets, PostgreSQL wait, foreground server.
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

set -euo pipefail

CASMGR_CONFIG="${CASMGR_CONFIG:-/etc/casmgr/config.json}"
CASMGR_SECRETS="${CASMGR_SECRETS:-/var/casmgr/secrets}"
CASMGR_WATCH_ROOT="${CASMGR_WATCH_ROOT:-/watched}"
PG_WAIT_SECONDS="${CASMGR_PG_WAIT_SECONDS:-120}"

if [[ -f "${CASMGR_SECRETS}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${CASMGR_SECRETS}/.env"
    set +a
fi

if [[ ! -f "${CASMGR_CONFIG}" ]]; then
    echo "ERROR: config not mounted at ${CASMGR_CONFIG}" >&2
    exit 1
fi

mkdir -p "${CASMGR_WATCH_ROOT}"

_pg_host_from_config() {
    python3 - <<'PY' "${CASMGR_CONFIG}"
import sys
from pathlib import Path

from code_analysis.core.config_json import load_config_json

cfg = load_config_json(Path(sys.argv[1]))
host = (
    cfg.get("code_analysis", {})
    .get("database", {})
    .get("driver", {})
    .get("config", {})
    .get("host", "")
)
print(str(host or "").strip())
PY
}

_pg_port_from_config() {
    python3 - <<'PY' "${CASMGR_CONFIG}"
import sys
from pathlib import Path

from code_analysis.core.config_json import load_config_json

cfg = load_config_json(Path(sys.argv[1]))
port = (
    cfg.get("code_analysis", {})
    .get("database", {})
    .get("driver", {})
    .get("config", {})
    .get("port", 5432)
)
print(int(port))
PY
}

wait_for_postgres() {
    local host port user tries
    host="${CODE_ANALYSIS_POSTGRES_HOST:-$(_pg_host_from_config)}"
    port="${CODE_ANALYSIS_POSTGRES_PORT:-$(_pg_port_from_config)}"
    user="${POSTGRES_USER:-postgres}"
    if [[ -z "${host}" || "${host}" == "127.0.0.1" || "${host}" == "localhost" ]]; then
        return 0
    fi
    export PGPASSWORD="${POSTGRES_SUPERUSER_PASSWORD:-${POSTGRES_PASSWORD:-${CODE_ANALYSIS_POSTGRES_PASSWORD:-}}}"
    tries="${PG_WAIT_SECONDS}"
    echo "Waiting for PostgreSQL at ${host}:${port} (up to ${tries}s) ..."
    while (( tries > 0 )); do
        if pg_isready -h "${host}" -p "${port}" -U "${user}" >/dev/null 2>&1; then
            echo "PostgreSQL is ready."
            return 0
        fi
        tries=$((tries - 1))
        sleep 1
    done
    echo "ERROR: PostgreSQL not ready on ${host}:${port}" >&2
    return 1
}

wait_for_postgres

exec python3 -m code_analysis.main --config "${CASMGR_CONFIG}" "$@"
