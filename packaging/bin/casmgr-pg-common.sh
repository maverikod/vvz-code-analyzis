#!/bin/bash
# Shared constants for casmgr PostgreSQL container helpers.
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

set -euo pipefail

CASMGR_ETC="${CASMGR_ETC:-/etc/casmgr}"
CASMGR_VAR="${CASMGR_VAR:-/var/casmgr}"
CASMGR_LOG="${CASMGR_LOG:-/var/log/casmgr}"
CASMGR_USER="${CASMGR_USER:-casuser}"
CASMGR_GROUP="${CASMGR_GROUP:-casgrp}"
CASMGR_PG_CONTAINER="${CASMGR_PG_CONTAINER:-casmgr-postgres}"
CASMGR_DOCKER_IMAGE_FILE="${CASMGR_DOCKER_IMAGE_FILE:-/usr/share/casmgr/docker-image}"
CASMGR_SECRETS="${CASMGR_SECRETS:-${CASMGR_VAR}/secrets}"
CASMGR_PG_DATA="${CASMGR_PG_DATA:-${CASMGR_VAR}/postgres/data}"
CASMGR_PG_CACHE="${CASMGR_PG_CACHE:-${CASMGR_VAR}/postgres/cache}"
CASMGR_PG_ETC="${CASMGR_PG_ETC:-${CASMGR_ETC}/postgres}"
CASMGR_PG_LOG="${CASMGR_PG_LOG:-${CASMGR_LOG}/postgres}"
CASMGR_CONFIG="${CASMGR_CONFIG:-${CASMGR_ETC}/config.json}"
CASMGR_SERVER_INSTALL="${CASMGR_SERVER_INSTALL:-/usr/lib/casmgr-server}"

casmgr_require_root_or_casuser() {
    local u
    u="$(id -un)"
    if [[ "$u" != "root" && "$u" != "$CASMGR_USER" ]]; then
        echo "ERROR: this command must be run as root or ${CASMGR_USER} (current: ${u})" >&2
        exit 1
    fi
}

casmgr_docker_image_ref() {
    if [[ ! -f "$CASMGR_DOCKER_IMAGE_FILE" ]]; then
        echo "ERROR: missing ${CASMGR_DOCKER_IMAGE_FILE} (reinstall casmgr-server package)" >&2
        exit 1
    fi
    tr -d '[:space:]' <"$CASMGR_DOCKER_IMAGE_FILE"
}

casmgr_load_secrets_env() {
    if [[ -f "${CASMGR_SECRETS}/.env" ]]; then
        set -a
        # shellcheck disable=SC1091
        source "${CASMGR_SECRETS}/.env"
        set +a
    fi
}

casmgr_ensure_pg_directories() {
    install -d -o "$CASMGR_USER" -g "$CASMGR_GROUP" -m 0750 \
        "$CASMGR_VAR" "$CASMGR_LOG" \
        "$CASMGR_PG_DATA" "$CASMGR_PG_CACHE" "$CASMGR_PG_LOG" \
        "$CASMGR_SECRETS" "$CASMGR_PG_ETC"
    if [[ -f "${CASMGR_SECRETS}/.env" ]]; then
        chown "$CASMGR_USER:$CASMGR_GROUP" "${CASMGR_SECRETS}/.env"
        chmod 0640 "${CASMGR_SECRETS}/.env"
    fi
}

casmgr_python() {
    local py="${CASMGR_SERVER_INSTALL}/.venv/bin/python"
    if [[ -x "$py" ]]; then
        echo "$py"
        return 0
    fi
    echo "python3"
}

casmgr_pg_host_port() {
    "$(casmgr_python)" - <<'PY' "$CASMGR_CONFIG"
import sys
from pathlib import Path

from code_analysis.core.config_json import load_config_json

path = Path(sys.argv[1])
cfg = load_config_json(path)
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

casmgr_wait_for_postgres() {
    local port tries=60
    port="$(casmgr_pg_host_port)"
    export PGHOST="${PGHOST:-127.0.0.1}"
    export PGPORT="${PGPORT:-$port}"
    export PGUSER="${PGUSER:-postgres}"
    casmgr_load_secrets_env
    export PGPASSWORD="${POSTGRES_SUPERUSER_PASSWORD:-${POSTGRES_PASSWORD:-}}"
    if [[ -z "${PGPASSWORD:-}" ]]; then
        echo "WARNING: POSTGRES_SUPERUSER_PASSWORD not set in ${CASMGR_SECRETS}/.env" >&2
    fi
    while (( tries > 0 )); do
        if pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" >/dev/null 2>&1; then
            return 0
        fi
        tries=$((tries - 1))
        sleep 1
    done
    echo "ERROR: PostgreSQL not ready on ${PGHOST}:${PGPORT}" >&2
    return 1
}

casmgr_python_for_admin() {
    if [[ -x "${CASMGR_SERVER_INSTALL}/.venv/bin/python" ]]; then
        echo "${CASMGR_SERVER_INSTALL}/.venv/bin/python"
    elif command -v python3 >/dev/null 2>&1; then
        echo python3
    else
        echo "ERROR: python3 not found" >&2
        exit 1
    fi
}
