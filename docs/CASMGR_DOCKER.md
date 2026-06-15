# Docker deployment — full stack in containers

Production can run **both** the MCP server and PostgreSQL in Docker. Application
code is baked into the **`casmgr-server`** image; nothing from the host checkout
is required at runtime except mounted configuration, secrets, logs, data, and
watched source trees.

Debian package deployment (server on host, PostgreSQL in Docker only) remains
documented in [CASMGR_DEPLOYMENT.md](CASMGR_DEPLOYMENT.md).

Author: Vasiliy Zdanovskiy — vasilyvz@gmail.com

## Images

| Image | Contents |
|-------|----------|
| `vasilyvz/casmgr-server:<version>` | Python app, `code_analysis` package, workers, MCP server |
| `vasilyvz/casmgr-postgres:<version>` | PostgreSQL 16 + pgvector |

Build from repository root:

```bash
docker build -f docker/casmgr-server/Dockerfile \
  --build-arg VERSION="$(python -c 'import tomllib; print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')" \
  -t vasilyvz/casmgr-server:TAG .

docker build -f docker/casmgr-postgres/Dockerfile \
  --build-arg VERSION=TAG \
  -t vasilyvz/casmgr-postgres:TAG .
```

Release pipeline (`./scripts/release_build.sh`) publishes **`casmgr-postgres`** and
**`casmgr-server`** with the same version tag as `pyproject.toml`.

## Mount contract

Inside the **`casmgr-server`** container:

| Container path | Host mount | Purpose |
|----------------|------------|---------|
| `/etc/casmgr/config.json` | `docker/runtime/etc/casmgr/` | MCP config (JSONC) + mTLS under `mtls/` |
| `/var/casmgr/secrets/.env` | `docker/runtime/secrets/` | PostgreSQL passwords |
| `/var/log/casmgr` | `docker/runtime/log/` | All application logs |
| `/var/casmgr/data`, `faiss`, `locks`, … | `docker/runtime/…` | Service state (not in image) |
| **`/watched/<watch_dir_uuid>/`** | **host watch root** | **One bind mount per UUID subdirectory** |

### Watched directories (host catalog → container mount root)

**Host (before container / systemd start):** run
``scripts/casmgr-prepare-watch-mounts.py`` (packaged as
``/usr/lib/casmgr-server/scripts/casmgr-prepare-watch-mounts.py``). It merges:

1. **``file_watcher.host_watch_catalog``** — immediate children that are UUID4-named
   directories/symlinks, plus non-UUID entries whose resolved path matches config.
2. **``code_analysis.worker.watch_dirs``** — explicit ``{id, path}`` on the host.

Then either creates symlinks under ``watch_mount_root`` (Debian host) or writes a
Compose override (``--compose-out docker/docker-compose.watch-mounts.yml``).

**Inside the container / server:** only **UUID4 direct children of
``watch_mount_root``** (default ``/watched``) are watch dirs — same scan as the
file watcher and ``list_projects``.

Fixed parent **`/watched`** (`CASMGR_DOCKER_WATCH_ROOT`). Mount mode is active when
``code_analysis.file_watcher.watch_mount_root`` is set or ``CASMGR_WATCH_ROOT`` env
is non-empty.

1. Scan direct subdirectories of ``watch_mount_root`` whose names are valid **UUID4**.
2. Each becomes a watch dir at ``/watched/{uuid}/``.
3. On each watcher init/cycle, sync DB with disk:
   - **New on disk** → insert watch_dir row + create `settings.json` with defaults.
   - **Absent on disk** → `watch_dirs.deleted = 1` and soft-delete all projects
     and files for that watch_dir.
   - **Reappeared on disk** → clear `watch_dirs.deleted` and
     `settings.json` `"deleted": false` only (projects/files stay deleted).

Each watch directory root must contain **`settings.json`**:

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

`ignore_patterns` apply per watch dir (project-relative matching in the scanner).
When the file is missing, the watcher creates it with the default pattern list
(see ``code_analysis.core.watch_dir_settings.DEFAULT_WATCH_DIR_IGNORE_PATTERNS``).

**Package template (trial catalog):** on install, ``debian/postinst`` copies
``packaging/watch-catalog-example/{uuid}/`` (shipped under
``/usr/share/casmgr-server/watch-catalog-example/``) into
``/var/casmgr/watch_catalog/{uuid}/`` when that entry does not exist yet.
The shipped ``settings.json`` is the reference ignore list. ``config.json.template``
includes a matching ``worker.watch_dirs`` entry pointing at that path; replace it
with your host tree and edit ``settings.json`` (or add per-dir overrides) as needed.

Host bind-mount exposes the **contents** of the host tree at that path:

```
host:/home/user/projects/tools  →  container:/watched/a6c47e01-…/
                                      ├── settings.json
                                      ├── project_a/
                                      └── project_b/
```

Docker Compose (see `docker/.env.example`):

```yaml
- ${HOST_WATCH_ROOT}:/watched/${WATCH_DIR_ID}:rw
```

Config (`docker/config/config.docker.json.template`):

```json
"file_watcher": {
  "watch_mount_root": "/watched"
},
"worker": {
  "watch_dirs": []
}
```

Do **not** list watch dirs under `worker.watch_dirs` in Docker — bind-mount
UUID directories under `/watched/` instead. Host deployment without
`watch_mount_root` keeps config-driven `worker.watch_dirs` unchanged.

## Quick start

```bash
./scripts/docker/init-runtime-layout.sh
python scripts/casmgr-prepare-watch-mounts.py \
  --config docker/runtime/etc/casmgr/config.json \
  --compose-out docker/docker-compose.watch-mounts.yml

# Edit docker/runtime/etc/casmgr/config.json (advertised_host, MCP proxy, watch dirs)
# Place mTLS files in docker/runtime/etc/casmgr/mtls/
# Set passwords in docker/runtime/secrets/.env

cd docker
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.watch-mounts.yml up -d --build
```

First-time database (from host, with `postgresql-client` or exec into postgres container):

```bash
docker exec -it casmgr-postgres psql -U postgres -d code_analysis
# or use casmgr-pg-init on a host that shares the same config/secrets mounts
```

Server runs in **foreground** inside the container (`--foreground`), PID 1 friendly
for Docker restarts.

## Compose environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `CASMGR_RUNTIME` | `docker/runtime` (relative to compose file) | Host state root |
| `HOST_WATCH_ROOT` | `/home/vasilyvz/projects/tools` | Host directory mounted at `/watched/${WATCH_DIR_ID}` |
| `WATCH_DIR_ID` | (see `docker/.env.example`) | Must equal `watch_dirs[].id` and path suffix |
| `CASMGR_SERVER_IMAGE` | `vasilyvz/casmgr-server:<pyproject version>` | Server image |
| `CASMGR_POSTGRES_IMAGE` | `vasilyvz/casmgr-postgres:<version>` | Postgres image |
| `CASMGR_MCP_PUBLISH` | `0.0.0.0:15010:15010` | Published MCP HTTPS port |
| `CASMGR_PG_PUBLISH` | `127.0.0.1:5432:5432` | Optional host access to PG |

## What stays in the image

- Python dependencies (`pip install -e .`)
- `code_analysis/` package and entrypoints
- Worker and MCP server code

## What is never in the image

- `config.json`, secrets, mTLS private keys
- Log files
- PostgreSQL data directory
- Watched project source trees (only mounted under `/watched/*`)

## Related

- [CASMGR_DEPLOYMENT.md](CASMGR_DEPLOYMENT.md) — Debian + host server layout
- `docker/config/config.docker.json.template` — starter config for containers
- `packaging/config.json.template` — host `/etc/casmgr` layout
