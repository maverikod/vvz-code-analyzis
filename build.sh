#!/bin/bash
# One-command release build after git clone: Docker Hub push + Debian package.
# Version from pyproject.toml. Skips PyPI client publish (use ./scripts/release_build.sh for full release).
# Local deb-only without Docker Hub: ./scripts/release_build.sh --deb-only --skip-docker-push
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/release_build.sh" --skip-pypi "$@"
