# Docker deployment — all-in-one container

Production runs PostgreSQL, the MCP daemon, and all workers inside a **single**
container (`vasilyvz/casmgr:<version>`), supervised by s6-overlay. Nothing from
the host checkout is required at runtime except the three bind-mounted
directories below.

Debian package deployment (thin installer + `casmgr.service`) is documented in
[CASMGR_DEPLOYMENT.md](CASMGR_DEPLOYMENT.md); this file covers the container
contract itself.

Author: Vasiliy Zdanovskiy — vasilyvz@gmail.com

## Image

| Image | Contents |
|-------|----------|
| `vasilyvz/casmgr:<version>` | PostgreSQL 16 + pgvector, `code_analysis` package, all workers, MCP server — supervised by s6-overlay v3 |

`<version>` is the app version from [pyproject.toml](../pyproject.toml) (currently `1.6.35`); the release pipeline also tags/pushes `latest`.

Build from repository root:

```bash
docker build -f docker/casmgr/Dockerfile \
  --build-arg VERSION="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')" \
  -t vasilyvz/casmgr:TAG .
```

Release pipeline (`./scripts/release_build.sh`) builds and pushes
`vasilyvz/casmgr:<pyproject version>` and `vasilyvz/casmgr:latest`.

## Supervision (s6-overlay)

PID 1 is s6-overlay v3 (`docker/casmgr/s6/s6-rc.d/`). Boot order:

1. `00-init-dirs` (root) — create missing directories; `chown -R 999:999`
   the PostgreSQL data/cache dirs (bind mount arrives casuser-root owned).
2. `05-init-user` (root, parallel with `00-init-dirs`) — creates `casuser`
   inside the image with uid/gid from `CASMGR_UID`/`CASMGR_GID`; chowns
   daemon-writable directories.
3. `10-pg-initdb` (root → `gosu postgres`) — `initdb` + `CREATE EXTENSION vector`
   on first boot (no `PG_VERSION` file yet).
4. `20-postgres` (longrun, `gosu postgres`) — `postgres -D /var/casmgr/postgres/data
   -c listen_addresses=127.0.0.1`; readiness = `pg_isready`.
5. `30-pg-init` (root, after PG ready) — ensures the app role/DB (`code_analysis`)
   and password from `/var/casmgr/secrets/.env`; idempotent.
6. `40-casmgr` (longrun, root → `gosu casuser`, waits on `30-pg-init` and
   `05-init-user`) — `code_analysis.main --config /etc/casmgr/config.json --foreground`.

On shutdown, PostgreSQL gets a clean `pg_ctl stop -m fast` before the
container exits (no WAL replay warning on next start).

## Process user model

s6-overlay's PID 1 starts as root only to perform init tasks (create
directories, fix ownership) and to run PostgreSQL, which drops to uid/gid 999
(`gosu postgres`). The `code_analysis` daemon itself never runs as root: its
`40-casmgr` service starts as root just long enough to `gosu` into `casuser`,
using the uid/gid injected at container start via the `CASMGR_UID`/
`CASMGR_GID` environment variables (read by
`docker/docker-compose.allinone.yml` from `/etc/casmgr/.env`). On a real
host, `debian/postinst` writes those two variables with the host
`casuser`/`casgrp` real numeric ids (`id -u casuser`, `getent group
casgrp`), so the daemon's in-container uid/gid always match the host
`casuser` that owns the bind-mounted trees. Files the daemon creates in
observed repositories (git objects, `versions/` snapshots, `trash/`, sidecar
`.cst`/`.tree` files without a source) are therefore owned `casuser:casgrp`,
matching the host — no root-owned artifacts, no `sudo` needed to edit them.

**Security note:** inside the container, `casuser` has passwordless `sudo`
to root (`/etc/sudoers.d/casuser`: `casuser ALL=(ALL) NOPASSWD: ALL`) for
admin/maintenance tasks. This is an intentional escalation path local to the
container's own user namespace — the daemon itself never exercises it during
normal operation, and it does not change the ownership model described above.

## Mount contract

Three bind mounts, all **casuser-root, rw**:

| Container path | Purpose |
|-----------------|---------|
| `/etc/casmgr` | `config.json`, `mtls/`, `docker-compose.yml` (this is what `casmgr.service` runs) |
| `/var/casmgr` | `secrets/.env`, `postgres/{data,cache}` (uid 999), `data/`, `faiss/`, `locks/`, `backups/`, `trash/`, `versions/`, `watch_catalog/`, `watched/<uuid4>/` |
| `/var/log/casmgr` | daemon logs + `postgres/` subdir |

Nothing else is mounted — no per-watch-dir compose overrides, no separate
PostgreSQL container.

### Watched directories

Only **UUID4-named direct children of `/var/casmgr/watched`** are watch dirs —
the same scan used by the file watcher and `list_projects`. Bind-mount (or
place) a host tree so its *contents* land directly under
`/var/casmgr/watched/<uuid4>/`:

```
host:/home/user/projects/tools  →  /var/casmgr/watched/a6c47e01-.../
                                      ├── settings.json
                                      ├── project_a/
                                      └── project_b/
```

Each watch directory root must contain `settings.json`:

```json
{
  "deleted": false,
  "ignore_patterns": [
    "**/.venv/**",
    "**/venv/**",
    "**/__pycache__/**"
  ]
}
```

When missing, the watcher creates it with the default pattern list (see
`code_analysis.core.watch_dir_settings.DEFAULT_WATCH_DIR_IGNORE_PATTERNS`).
On each watcher cycle the DB is synced with disk: new UUID dirs are inserted,
directories removed from disk soft-delete their watch_dir/projects/files, and
directories that reappear are un-deleted (projects/files stay deleted).

Do **not** list watch dirs under `code_analysis.worker.watch_dirs` for this
deployment — bind-mount UUID directories under `/var/casmgr/watched/` instead.

## Lifecycle

Everything on the host is `casmgr.service` (systemd, installed by the `.deb`)
wrapping a single `docker compose` stack:

```bash
sudo systemctl start casmgr      # docker compose -f /etc/casmgr/docker-compose.yml up -d
sudo systemctl stop casmgr       # ... down
sudo systemctl restart casmgr
docker logs -f casmgr            # daemon + postgres logs (foreground process)
```

There is no separate PostgreSQL container/unit — `casmgr-postgres` no longer
exists. `docker/docker-compose.allinone.yml` is installed as
`/etc/casmgr/docker-compose.yml`; do not run `docker compose` from a different
compose file for this deployment.

## Quick start (manual, without the .deb)

```bash
mkdir -p /etc/casmgr /var/casmgr /var/log/casmgr
cp docker/config/config.docker.json.template /etc/casmgr/config.json
# edit /etc/casmgr/config.json: advertised_host, registration URLs, mTLS paths
mkdir -p /etc/casmgr/mtls   # place server.crt/server.key/ca.crt/client.crt/client.key
cat > /var/casmgr/secrets/.env <<'EOF'
POSTGRES_SUPERUSER_PASSWORD=change_me_superuser
CODE_ANALYSIS_POSTGRES_PASSWORD=change_me_app
POSTGRES_DB=code_analysis
EOF

export CASMGR_VERSION=1.6.35   # or omit for :latest
docker compose -f docker/docker-compose.allinone.yml up -d
```

First-time database check:

```bash
docker exec casmgr gosu postgres psql -U postgres -d code_analysis -c '\dx'
```

Confirm the daemon (mTLS JSON-RPC, port 15010):

```bash
curl --cacert /etc/casmgr/mtls/ca.crt --cert /etc/casmgr/mtls/client.crt \
     --key /etc/casmgr/mtls/client.key \
     https://127.0.0.1:15010/ -d '{"jsonrpc":"2.0","method":"health_check","id":1}'
```

## Port

The container publishes **15010** (HTTPS + mTLS) — `0.0.0.0:15010:15010` in
`docker/docker-compose.allinone.yml`.

## External services (unchanged)

`config.json` still carries placeholders for services outside this container —
edit them before starting:

- `advertised_host` — this host's IP/DNS name
- `registration.*` — MCP proxy registration/heartbeat URLs and `instance_uuid`
- mTLS material under `/etc/casmgr/mtls/` (`server.crt`, `server.key`, `ca.crt`,
  `client.crt`, `client.key`)
- `chunker` (default `:8009`) and `embedding` (default `:8001`) service endpoints

## What stays in the image

- Python dependencies (isolated venv at `/opt/casmgr/venv`, `pip install -e ".[postgres-backup]"`)
- `code_analysis/` package, `casmgr_entry`, worker and MCP server code
- s6-overlay service tree and PostgreSQL binaries (from the `pgvector/pgvector:pg16` base)

## What is never in the image

- `config.json`, secrets, mTLS private keys
- Log files
- PostgreSQL data directory
- Watched project source trees (only mounted under `/var/casmgr/watched/*`)

## Related

- [CASMGR_DEPLOYMENT.md](CASMGR_DEPLOYMENT.md) — Debian install + `casmgr.service` lifecycle
- `docker/casmgr/Dockerfile` — image build
- `docker/docker-compose.allinone.yml` — the compose stack installed as `/etc/casmgr/docker-compose.yml`
- `docker/config/config.docker.json.template` — starter config
