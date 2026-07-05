# Building and Installing casmgr-server (Debian + Docker)

## One command after git clone

```bash
git clone https://github.com/vasilyvz/code_analysis.git
cd code_analysis
./build.sh
```

The script installs missing build packages via `sudo apt-get`, reads the version from
`pyproject.toml`, and writes `../casmgr-server_<version>-1_all.deb`.

Install the package:

```bash
sudo dpkg -i ../casmgr-server_*.deb
sudo apt-get install -f
```

The `.deb` is a **thin installer**: it lays out `/etc/casmgr`, `/var/casmgr`,
`/var/log/casmgr`, generates PostgreSQL passwords, installs
`docker/docker-compose.allinone.yml` as `/etc/casmgr/docker-compose.yml`, pulls
the `vasilyvz/casmgr:<version>` image, and enables the single `casmgr.service`
unit. There is no application code or Python venv on the host — everything
runs inside the container.

## Full release (Docker + deb + PyPI client)

Builds the single `vasilyvz/casmgr` Docker image, pushes it to Hub (both the
version tag and `latest`), builds the Debian package, and uploads
**code-analysis-client** to PyPI (same version as root `pyproject.toml`):

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-...   # API token

./scripts/release_build.sh
# explicit version:
./scripts/release_build.sh 1.6.35
```

Skip PyPI: `./scripts/release_build.sh --skip-pypi`
Deb-only + PyPI: `./scripts/release_build.sh --deb-only --pypi`
Build client wheel only (no upload): `./scripts/publish_code_analysis_client_pypi.sh --check-only`

Environment:

- `CASMGR_DOCKER_REGISTRY` — default `vasilyvz`
- `CASMGR_DOCKER_IMAGE_NAME` — default `casmgr`

## Options

| Command | Effect |
|---------|--------|
| `./build.sh` | deb only, version from `pyproject.toml` |
| `./scripts/release_build.sh --deb-only` | same as `./build.sh` |
| `./scripts/release_build.sh` | Docker build/push (single image) + deb |
| `./scripts/release_build.sh --skip-deps` | do not run `apt-get` (CI) |

Disable auto-install:

```bash
CASMGR_SKIP_BUILD_DEPS=1 ./build.sh
```

Packages installed when needed (on the **build** machine, not inside the image):

- **Python:** `python3`, `python3-venv`, `python3-pip` (functional venv/pip test)
- **Runtime:** `openssl`, `ca-certificates`, `adduser`, `rsync`, `postgresql-client`
- **Deb build:** `devscripts`, `debhelper`, `texinfo`
- **Docker release:** `docker.io`

The image itself builds its own isolated venv at `/opt/casmgr/venv` from
`docker/casmgr/Dockerfile` (`pip install -e ".[postgres-backup]"`) — the deb
package ships no Python dependencies for the host.

## Documentation

- `docs/CASMGR_DEPLOYMENT.md`
- `docs/CASMGR_DOCKER.md`
- `man casmgr-server`
- `info casmgr-server`

## Package contents

- **casmgr.service** — single systemd unit; `docker compose -f /etc/casmgr/docker-compose.yml up -d` / `down`
- **Admin scripts** in `/usr/lib/casmgr/bin/`
- **Pinned image** in `/usr/share/casmgr/docker-image`
- **casuser uid/gid** — `postinst` writes `CASMGR_UID`/`CASMGR_GID` (the host
  casuser's real numeric ids) into `/etc/casmgr/.env`, so the container
  daemon (which runs as `casuser`, not root) matches host file ownership
