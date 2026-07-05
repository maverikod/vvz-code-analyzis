#!/command/with-contenv bash
# Oneshot (root): ensure the /var/casmgr and /var/log/casmgr subtrees exist.
# The bind-mounted /var/casmgr arrives owned by the host's casuser-root; the
# PostgreSQL data/cache subtrees get uid/gid 999 (this image's "postgres" user)
# here. Everything else (daemon-writable state dirs) is chowned to
# CASMGR_UID:CASMGR_GID by 05-init-user, which runs next.
set -euo pipefail

for d in \
    /var/casmgr/postgres/data \
    /var/casmgr/postgres/cache \
    /var/casmgr/data \
    /var/casmgr/faiss \
    /var/casmgr/locks \
    /var/casmgr/backups \
    /var/casmgr/trash \
    /var/casmgr/versions \
    /var/casmgr/watch_catalog \
    /var/casmgr/watched \
    /var/log/casmgr/postgres
do
    mkdir -p "$d"
done

chown -R 999:999 /var/casmgr/postgres/data /var/casmgr/postgres/cache

# PostgreSQL runs as uid 999 and reaches its data dir THROUGH /var/casmgr and
# /var/casmgr/postgres. The bind-mounted /var/casmgr arrives 0750 casuser:casgrp
# on a packaged host, so uid 999 (neither owner nor in casgrp) gets EACCES on
# the data dir it owns. Grant traverse-only (o+x, NOT read) on the path
# components so postgres can descend; contents stay unreadable to "other".
chmod o+x /var/casmgr /var/casmgr/postgres 2>/dev/null || true

echo "00-init-dirs: directories ready."
