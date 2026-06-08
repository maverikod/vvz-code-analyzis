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

## Full release (Docker + deb)

Builds Docker image, pushes to Hub, and creates a Debian package with the **same version tag**:

```bash
./scripts/release_build.sh
# explicit version:
./scripts/release_build.sh 1.0.7
```

Environment:

- `CASMGR_DOCKER_REGISTRY` — default `vasilyvz`
- `CASMGR_DOCKER_IMAGE_NAME` — default `casmgr-postgres`

## Options

| Command | Effect |
|---------|--------|
| `./build.sh` | deb only, version from `pyproject.toml` |
| `./scripts/release_build.sh --deb-only` | same as `./build.sh` |
| `./scripts/release_build.sh` | Docker build/push + deb |
| `./scripts/release_build.sh --skip-deps` | do not run `apt-get` (CI) |

Disable auto-install:

```bash
CASMGR_SKIP_BUILD_DEPS=1 ./build.sh
```

Packages installed when needed:

- **Python:** `python3`, `python3-venv`, `python3-pip` (functional venv/pip test)
- **Runtime:** `openssl`, `ca-certificates`, `adduser`, `rsync`, `postgresql-client`
- **Deb build:** `devscripts`, `debhelper`, `texinfo`
- **Docker release:** `docker.io`

Pip dependencies from `pyproject.toml` are installed into the app venv at `postinst`, not at build time.

## Documentation

- `docs/CASMGR_DEPLOYMENT.md`
- `man casmgr-server`
- `info casmgr-server`

## Package contents

- **casmgr-server.service** — MCP daemon (`casuser`)
- **casmgr-postgres.service** — PostgreSQL Docker container
- **Admin scripts** in `/usr/lib/casmgr/bin/`
- **Pinned image** in `/usr/share/casmgr/docker-image`
