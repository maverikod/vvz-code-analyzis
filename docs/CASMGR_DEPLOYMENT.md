# casmgr-server — production deployment

Full reference: `man casmgr-server`, `info casmgr-server`, and this file.

## Layout

| Path | Purpose |
|------|---------|
| `/etc/casmgr/config.json` | MCP server configuration (**conffile**) |
| `/var/casmgr/secrets/.env` | PostgreSQL passwords (**conffile**) |
| `/var/casmgr/postgres/data` | PG data (bind mount, uid 999) |
| `/var/casmgr/postgres/cache` | PG cache (bind mount, uid 999) |
| `/var/log/casmgr` | Application logs |
| `/var/log/casmgr/postgres` | PostgreSQL logs in container |
| `/usr/share/casmgr/docker-image` | Pinned image ref (`registry/name:tag`) |
| `/usr/lib/casmgr/bin/` | Admin scripts (also in `/usr/sbin/`) |

## Upgrade from `code-analysis-server`

The `casmgr-server` package **Provides/Replaces/Conflicts** with the old
`code-analysis-server` name. On upgrade, legacy systemd unit
`code-analysis-server.service` is disabled; use `casmgr-server.service`.

Application code lives under `/usr/lib/casmgr-server` (venv created at install).

## Release build (version = Docker tag)

After git clone, build the Debian package with one command:

```bash
./build.sh
```

Version is taken from `pyproject.toml`. Build dependencies are installed automatically
via `sudo apt-get` when needed.

Full release (Docker push + deb):

```bash
./scripts/release_build.sh
# optional: CASMGR_DOCKER_REGISTRY=myuser
# flags: --deb-only | --docker-only | --skip-deps
```

Build details: `DEB_BUILD_README.md`, `scripts/casmgr_ensure_build_deps.sh`.

Produces:

- Docker image `vasilyvz/casmgr-postgres:1.0.6` (pushed to Hub)
- Debian package `casmgr-server_1.0.6-1_all.deb`

## Install

```bash
sudo dpkg -i casmgr-server_1.0.6-1_all.deb
sudo apt-get install -f
```

Automatic steps: pull image, recreate container, init DB, enable systemd.
**`casmgr-server` is not started** until `/etc/casmgr/config.json` has no
`CHANGE_ME` / `MCP_PROXY_HOST` placeholders and mTLS files exist under
`/etc/casmgr/mtls/`. PostgreSQL (`casmgr-postgres`) starts when Docker is available.

## Admin commands

```bash
sudo casmgr-postgres-container pull|recreate|start|stop|remove|status
sudo casmgr-pg-init [--fix-existing-db-owner]
sudo casmgr-pg-set-password
sudo systemctl restart casmgr-postgres casmgr-server
```

## Remove / purge

- `apt remove casmgr-server` — stops services, removes container, keeps image and `/var/casmgr`
- `apt purge casmgr-server` — also `docker rmi` for the pinned tag

## Configuration checklist

1. Edit `/etc/casmgr/config.json` (registration, mTLS, `watch_dirs`)
2. Place certificates under `/etc/casmgr/mtls/`
3. Confirm `/var/casmgr/secrets/.env` passwords (auto-generated on first install)
4. `sudo casmgr-pg-init` after password changes
5. `sudo systemctl start casmgr-server`

Author: Vasiliy Zdanovskiy — vasilyvz@gmail.com
