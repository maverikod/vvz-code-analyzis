# casmgr — production deployment

Full reference: **`man casmgr-server`**, **`man casmgr-config`**, **`info casmgr-server`** (config sections, secrets, mTLS, admin commands, config generator), and this file.

## Layout

| Path | Purpose |
|------|---------|
| `/etc/casmgr/config.json` | MCP server configuration (**conffile**) |
| `/etc/casmgr/docker-compose.yml` | Installed from `docker/docker-compose.allinone.yml`; what `casmgr.service` runs |
| `/etc/casmgr/mtls/` | mTLS certificates/keys |
| `/var/casmgr/secrets/.env` | PostgreSQL passwords (**conffile**) |
| `/var/casmgr/postgres/data` | PG data (bind mount, uid 999) |
| `/var/casmgr/postgres/cache` | PG cache (bind mount, uid 999) |
| `/var/casmgr/watched/<uuid4>/` | Observed source trees (bind-mount contents here) |
| `/var/log/casmgr` | Application logs |
| `/var/log/casmgr/postgres` | PostgreSQL logs in container |
| `/usr/share/casmgr/docker-image` | Pinned image ref (`registry/name:tag`) |
| `/usr/lib/casmgr/bin/` | Admin scripts (also in `/usr/sbin/`) |

**All-in-one container contract** (image contents, mount details, watch-dir
scan, s6-overlay boot order): see [CASMGR_DOCKER.md](CASMGR_DOCKER.md).

Everything runs inside **one container** (`vasilyvz/casmgr:<version>`):
PostgreSQL 16 + pgvector (uid 999) and the `code_analysis` daemon with all
workers, running as `casuser` (uid/gid matched to the host casuser via
`CASMGR_UID`/`CASMGR_GID`, dropped via `gosu` from the container's root
PID 1). The host only needs Docker and one systemd unit, `casmgr.service` —
there is no host venv and no separate PostgreSQL container/unit. Inside the
container, `casuser` retains passwordless `sudo` to root for admin/maintenance
tasks (see [CASMGR_DOCKER.md](CASMGR_DOCKER.md) — Process user model).

## Upgrade from `code-analysis-server`

The `casmgr` package **Provides/Replaces/Conflicts** with the old
`code-analysis-server` name. On upgrade, legacy systemd unit
`code-analysis-server.service` is disabled; use `casmgr.service`.

## Release build (image tag = app version)

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

Produces (example, version from `pyproject.toml`, currently `1.6.35`):

- Docker image `vasilyvz/casmgr:1.6.35` and `vasilyvz/casmgr:latest` (pushed to Hub)
- Debian package `casmgr-server_1.6.35-1_all.deb`

## Install

```bash
sudo dpkg -i casmgr-server_1.6.35-1_all.deb
sudo apt-get install -f
```

Automatic steps: pull the `casmgr` image, write `/etc/casmgr/docker-compose.yml`,
write the host `casuser`'s uid/gid (`CASMGR_UID`/`CASMGR_GID`) into
`/etc/casmgr/.env` so the container daemon matches host file ownership,
generate PostgreSQL passwords, enable `casmgr.service`.
**`casmgr` is not started** until `/etc/casmgr/config.json` has no
`CHANGE_ME` / `MCP_PROXY_HOST` placeholders and mTLS files exist under
`/etc/casmgr/mtls/`.

After `dpkg` finishes, read the **post-install banner** on the terminal: it lists
placeholders to replace, password files, and start commands.

## First install checklist

1. **`/etc/casmgr/config.json`** — replace placeholders:
   - `server.advertised_host`: `CHANGE_ME` → this host's IP or DNS name
   - `registration.*` URLs: `MCP_PROXY_HOST` → MCP proxy hostname/IP
   - `chunker`/`embedding` endpoints if not using the defaults (`:8009`/`:8001`)
2. **`/var/casmgr/secrets/.env`** — PostgreSQL passwords:
   - On first install, random passwords are generated if the file is new
   - Back them up securely, or set your own `POSTGRES_*` values
   - Apply to the cluster: `sudo casmgr-pg-set-password`
3. **mTLS** — place `server.crt`, `server.key`, `ca.crt`, `client.crt`, `client.key`
   under `/etc/casmgr/mtls/` (permissions applied by `dpkg --configure`)
4. **Watched directories** — bind-mount host source trees so their contents
   land under `/var/casmgr/watched/<uuid4>/` (see
   [CASMGR_DOCKER.md](CASMGR_DOCKER.md#watched-directories))
5. **Start** (if the package did not start it automatically):

   ```bash
   sudo systemctl start casmgr
   ```

### Password rotation

Edit `/var/casmgr/secrets/.env`, then:

```bash
sudo casmgr-pg-set-password
```

This applies **both** `POSTGRES_SUPERUSER_PASSWORD` and `CODE_ANALYSIS_POSTGRES_PASSWORD`.
When rotating the superuser password, set `POSTGRES_SUPERUSER_CONNECT_PASSWORD` to the
**current** cluster password for that run (see `secrets.env.template`).

Superuser only: `sudo casmgr-pg-set-password --superuser-only`

## Admin commands

```bash
sudo systemctl start|stop|restart|status casmgr
docker logs -f casmgr
docker exec casmgr gosu postgres psql -U postgres -d code_analysis
sudo casmgr-pg-set-password [--superuser-only]
```

`casmgr.service` wraps `docker compose -f /etc/casmgr/docker-compose.yml`
(`up -d` on start, `down` on stop); there is no separate `casmgr-postgres`
service or container to manage.

## Remove / purge

- `apt remove casmgr-server` — stops `casmgr.service` (`docker compose down`), keeps the image and `/var/casmgr`
- `apt purge casmgr-server` — also `docker rmi` for the pinned tag

## Port and registration defaults

On one host, production and development must not collide on MCP listen port or
proxy `server_id`.

| Role | Config file | MCP port | `registration.server_id` |
|------|-------------|----------|---------------------------|
| Production (`casmgr` container) | `/etc/casmgr/config.json` | **15010** | `code-analysis-server` |
| Development (git checkout) | `./config.json` | **15000** | `code-analysis-server-dev` |
| PostgreSQL (in-container) | `code_analysis.database.driver` | **5432** on `127.0.0.1` (inside the container) | — |

When both servers share the packaged PostgreSQL (dev pointed at the packaged
container's exposed port, if any), keep **distinct**
`registration.instance_uuid` values (auto-generated on first package install for
production).

Fresh installs ship `/etc/casmgr/config.json` with port **15010**.

## Configuration checklist

1. Edit `/etc/casmgr/config.json` (registration, mTLS, external service endpoints)
2. Place certificates under `/etc/casmgr/mtls/` (`server.crt`, `server.key`, `ca.crt`, `client.crt`, `client.key`)
3. Ensure permissions allow the container to read private keys (mode `0640`
   under `/etc/casmgr/mtls`, applied automatically by `dpkg --configure`)
4. Confirm `/var/casmgr/secrets/.env` passwords (auto-generated on first install)
5. `sudo casmgr-pg-set-password` after editing passwords
6. `sudo systemctl start casmgr`

## Troubleshooting

### `Address already in use` on start

Production listens on **15010** by default; the dev checkout uses **15000**.
If both are configured for the same port, stop one instance or align ports per the
table in [Port and registration defaults](#port-and-registration-defaults).

```bash
cd ~/projects/tools/code_analysis
casmgr --config config.json stop
# or: pkill -f 'code_analysis.main --config config.json'
sudo systemctl restart casmgr
```

Check listeners:

```bash
ss -tlnp | grep -E '15000|15010'
```

### `pg_advisory_unlock` / `Database is unavailable` (watch_dirs)

If the log shows `no unique constraint matching given keys for referenced table "watch_dirs"`,
the PostgreSQL schema migration left `watch_dirs` without a primary key. Re-run configure after
upgrading the package, or repair manually (replace `INSTANCE_UUID` with
`registration.instance_uuid` from config):

```bash
docker exec -it casmgr gosu postgres psql -U postgres -d code_analysis <<'SQL'
UPDATE watch_dirs SET server_instance_id = 'INSTANCE_UUID' WHERE server_instance_id IS NULL;
UPDATE watch_dir_paths wdp
SET server_instance_id = wd.server_instance_id
FROM watch_dirs wd
WHERE wdp.watch_dir_id = wd.id AND wdp.server_instance_id IS NULL;
UPDATE projects p
SET server_instance_id = wd.server_instance_id
FROM watch_dirs wd
WHERE p.watch_dir_id = wd.id AND p.server_instance_id IS NULL;
ALTER TABLE watch_dirs DROP CONSTRAINT IF EXISTS watch_dirs_pkey;
ALTER TABLE watch_dirs ADD PRIMARY KEY (server_instance_id, id);
SQL
sudo systemctl restart casmgr
```

### Missing Python modules / daemon crash-loops after install

The application venv lives **inside the image**, not on the host. If the
daemon fails to start, check `docker logs casmgr` first; a broken venv means
the image itself needs rebuilding/re-pulling rather than a host `dpkg
--configure`:

```bash
docker logs --tail 200 casmgr
sudo systemctl restart casmgr
```

Author: Vasiliy Zdanovskiy — vasilyvz@gmail.com
