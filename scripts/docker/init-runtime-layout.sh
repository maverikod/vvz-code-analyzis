#!/usr/bin/env bash
# Prepare host directories for docker compose bind mounts (config, logs, /watched/*).
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="${CASMGR_RUNTIME:-${ROOT}/docker/runtime}"

mkdir -p \
    "${RUNTIME}/etc/casmgr/mtls" \
    "${RUNTIME}/secrets" \
    "${RUNTIME}/log/postgres" \
    "${RUNTIME}/data/batch_output" \
    "${RUNTIME}/postgres/data" \
    "${RUNTIME}/postgres/cache" \
    "${RUNTIME}/faiss" \
    "${RUNTIME}/locks" \
    "${RUNTIME}/backups" \
    "${RUNTIME}/trash" \
    "${RUNTIME}/versions" \
    "${RUNTIME}/watched"

if [[ ! -f "${RUNTIME}/etc/casmgr/config.json" ]]; then
    cp "${ROOT}/docker/config/config.docker.json.template" \
        "${RUNTIME}/etc/casmgr/config.json"
    echo "Created ${RUNTIME}/etc/casmgr/config.json — edit placeholders."
fi

if [[ ! -f "${RUNTIME}/secrets/.env" ]]; then
    if [[ -f "${ROOT}/packaging/secrets.env.template" ]]; then
        cp "${ROOT}/packaging/secrets.env.template" "${RUNTIME}/secrets/.env"
    else
        cat >"${RUNTIME}/secrets/.env" <<'EOF'
POSTGRES_SUPERUSER_PASSWORD=change_me_superuser
CODE_ANALYSIS_POSTGRES_PASSWORD=change_me_app
POSTGRES_DB=code_analysis
EOF
    fi
    echo "Created ${RUNTIME}/secrets/.env — set passwords before first start."
fi

cat <<EOF

Runtime layout: ${RUNTIME}

Mount contract inside casmgr-server:
  /etc/casmgr/config.json     ← ${RUNTIME}/etc/casmgr/config.json
  /var/casmgr/secrets/.env    ← ${RUNTIME}/secrets/.env
  /var/log/casmgr             ← ${RUNTIME}/log
  /var/casmgr/data            ← ${RUNTIME}/data
  /watched/<watch_dir_uuid>/  ← host tree (contents of watched root)

Each watch_dirs entry:
  id   = UUID
  path = /watched/<same-uuid>
That path is written to watch_dir_paths.absolute_path on startup.

Compose (one mount per watch dir):
  \${HOST_WATCH_ROOT}:/watched/\${WATCH_DIR_ID}:rw

Copy docker/.env.example → docker/.env and align WATCH_DIR_ID with config.

EOF
