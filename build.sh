#!/bin/bash
# One-command Debian package build after git clone.
# Installs build dependencies via sudo when needed; version from pyproject.toml.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/release_build.sh" --deb-only "$@"
