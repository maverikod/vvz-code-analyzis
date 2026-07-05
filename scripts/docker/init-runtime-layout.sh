#!/usr/bin/env bash
# Prepare a local host directory tree for the all-in-one casmgr container, so
# docker/docker-compose.allinone.yml can be tested from a repo checkout without
# the packaged /etc/casmgr + /var/casmgr + /var/log/casmgr layout.
#
# It creates the three bind-mount roots (etc/casmgr, var/casmgr, var/log/casmgr)
# under a local RUNTIME directory. Point the bind mounts in a copy of
# docker/docker-compose.allinone.yml at these paths (see the note printed at the
# end and docker/.env.example).
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME="${CASMGR_RUNTIME:-${ROOT}/docker/runtime}"

ETC="${RUNTIME}/etc/casmgr"
VAR="${RUNTIME}/var/casmgr"
LOG="${RUNTIME}/var/log/casmgr"

mkdir -p \
    "${ETC}/mtls" \
    "${VAR}/secrets" \
    "${VAR}/postgres/data" \
    "${VAR}/postgres/cache" \
    "${VAR}/data" \
    "${VAR}/faiss" \
    "${VAR}/locks" \
    "${VAR}/backups" \
    "${VAR}/trash" \
    "${VAR}/versions" \
    "${VAR}/watch_catalog" \
    "${VAR}/watched" \
    "${LOG}/postgres"

if [[ ! -f "${ETC}/config.json" ]]; then
    cp "${ROOT}/docker/config/config.docker.json.template" \
        "${ETC}/config.json"
    echo "Created ${ETC}/config.json — edit placeholders."
fi

if [[ ! -f "${VAR}/secrets/.env" ]]; then
    if [[ -f "${ROOT}/packaging/secrets.env.template" ]]; then
        cp "${ROOT}/packaging/secrets.env.template" "${VAR}/secrets/.env"
    else
        cat >"${VAR}/secrets/.env" <<'EOF'
POSTGRES_SUPERUSER_PASSWORD=change_me_superuser
CODE_ANALYSIS_POSTGRES_PASSWORD=change_me_app
POSTGRES_DB=code_analysis
EOF
    fi
    echo "Created ${VAR}/secrets/.env — set passwords before first start."
fi

# PostgreSQL runs as uid/gid 999 inside the container; its data/cache dirs must
# be owned accordingly (the container's 00-init-dirs also chowns these, but set
# them here too so a rootless local test does not trip on permissions).
if command -v chown >/dev/null 2>&1; then
    chown -R 999:999 "${VAR}/postgres" 2>/dev/null \
        || echo "Note: could not chown ${VAR}/postgres to 999:999 (run with sudo if PG fails to start)."
fi

cat <<EOF

Runtime layout: ${RUNTIME}

All-in-one mount contract (three bind mounts, casuser-root, rw):
  /etc/casmgr       ← ${ETC}
  /var/casmgr       ← ${VAR}
  /var/log/casmgr   ← ${LOG}

Watched directories are UUID4 children of /var/casmgr/watched:
  place/mount a source tree so its contents land at ${VAR}/watched/<uuid4>/

To test docker/docker-compose.allinone.yml against this tree, copy it and
replace the three absolute bind-mount source paths (/etc/casmgr, /var/casmgr,
/var/log/casmgr) with the paths above, then:

  cp docker/.env.example docker/.env   # set passwords + CASMGR_VERSION
  docker compose -f <your-copy>.yml up -d

The packaged install (casmgr.service) uses the real /etc/casmgr, /var/casmgr,
and /var/log/casmgr directly and does not need this script.

EOF
