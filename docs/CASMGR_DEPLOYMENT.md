# casmgr-server — production deployment

Full reference: **`man casmgr-server`**, **`man casmgr-config`**, **`info casmgr-server`** (config sections, secrets, mTLS, admin commands, config generator), and this file.

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

**Full Docker stack** (server + PostgreSQL in containers, `/watched/*` mount
contract): see [CASMGR_DOCKER.md](CASMGR_DOCKER.md).

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

After `dpkg` finishes, read the **post-install banner** on the terminal: it lists
placeholders to replace, password files, and start commands.

## First install checklist

1. **`/etc/casmgr/config.json`** — replace placeholders:
   - `server.advertised_host`: `CHANGE_ME` → this host's IP or DNS name
   - `registration.*` URLs: `MCP_PROXY_HOST` → MCP proxy hostname/IP
   - `code_analysis.worker.watch_dirs` — project roots to index
2. **`/var/casmgr/secrets/.env`** — PostgreSQL passwords:
   - On first install, random passwords are generated if the file is new
   - Back them up securely, or set your own `POSTGRES_*` values
   - Apply to the cluster: `sudo casmgr-pg-set-password`
   - First DB/role creation: `sudo casmgr-pg-init`
3. **mTLS** — place `server.crt`, `server.key`, `ca.crt`, `client.crt`, `client.key`
   under `/etc/casmgr/mtls/` (permissions applied by `dpkg --configure`)
4. **Start** (if the package did not start the MCP server automatically):

   ```bash
   sudo systemctl start casmgr-postgres
   sudo casmgr-pg-init
   sudo systemctl start casmgr-server
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
sudo casmgr-postgres-container pull|recreate|start|stop|remove|status
sudo casmgr-pg-init [--fix-existing-db-owner]
sudo casmgr-pg-set-password [--superuser-only]
sudo systemctl restart casmgr-postgres casmgr-server
```

## Remove / purge

- `apt remove casmgr-server` — stops services, removes container, keeps image and `/var/casmgr`
- `apt purge casmgr-server` — also `docker rmi` for the pinned tag

## Port and registration defaults

On one host, production and development must not collide on MCP listen port or
proxy `server_id`.

| Role | Config file | MCP port | `registration.server_id` |
|------|-------------|----------|---------------------------|
| Production (`casmgr-server`) | `/etc/casmgr/config.json` | **15010** | `code-analysis-server` |
| Development (git checkout) | `./config.json` | **15000** | `code-analysis-server-dev` |
| PostgreSQL (Docker) | both use `code_analysis.database.driver` | **5432** on `127.0.0.1` | — |

When both servers share the packaged PostgreSQL container, keep **distinct**
`registration.instance_uuid` values (auto-generated on first package install for
production).

Fresh installs ship `/etc/casmgr/config.json` with port **15010**. Upgrades keep
your existing conffile; change `server.port` and `code_analysis.port` to **15010**
if you still use **15000** and run the dev server on the same machine.

## Configuration checklist

1. Edit `/etc/casmgr/config.json` (registration, mTLS, `watch_dirs`)
2. Place certificates under `/etc/casmgr/mtls/` (`server.crt`, `server.key`, `ca.crt`, `client.crt`, `client.key`)
3. Ensure `casuser` can read private keys (group `casgrp`, mode `0640`):

   ```bash
   sudo chown root:casgrp /etc/casmgr/mtls /etc/casmgr/mtls/*
   sudo chmod 0750 /etc/casmgr/mtls
   sudo chmod 0640 /etc/casmgr/mtls/*
   ```

   `dpkg --configure casmgr-server` applies these permissions automatically on upgrade.
4. Confirm `/var/casmgr/secrets/.env` passwords (auto-generated on first install)
5. `sudo casmgr-pg-set-password` after editing passwords; `sudo casmgr-pg-init` on first DB setup
6. `sudo systemctl start casmgr-server`

## Troubleshooting

### `Address already in use` on start

Production listens on **15010** by default; the dev checkout uses **15000**.
If both are configured for the same port, stop one instance or align ports per the
table in [Port and registration defaults](#port-and-registration-defaults).

```bash
cd ~/projects/tools/code_analysis
casmgr --config config.json stop
# or: pkill -f 'code_analysis.main --config config.json'
sudo systemctl restart casmgr-server
```

Check listeners:

```bash
ss -tlnp | grep -E '15000|15010'
```

### `pg_advisory_unlock` / `Database is unavailable` (watch_dirs)

If journal shows `no unique constraint matching given keys for referenced table "watch_dirs"`,
the PostgreSQL schema migration left `watch_dirs` without a primary key. Re-run configure after
upgrading the package, or repair manually (replace `INSTANCE_UUID` with
`registration.instance_uuid` from config):

```bash
sudo docker exec -it casmgr-postgres psql -U postgres -d code_analysis <<'SQL'
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
sudo systemctl restart casmgr-server
```

### Missing Python modules after install

Re-run package configure (reinstalls pip deps and verifies imports):

```bash
sudo dpkg --configure casmgr-server
```

Author: Vasiliy Zdanovskiy — vasilyvz@gmail.com
