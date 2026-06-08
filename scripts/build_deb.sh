#!/bin/bash
# Build casmgr-server .deb from pyproject.toml version (deb-only, no Docker push).
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/release_build.sh" --deb-only "$@"
