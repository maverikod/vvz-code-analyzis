#!/bin/bash
# Generate packaging/info/casmgr-server.info from Texinfo source.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export CASMGR_ROOT="$ROOT"
# shellcheck source=casmgr_ensure_build_deps.sh
source "${ROOT}/scripts/casmgr_ensure_build_deps.sh"
casmgr_ensure_build_deps --info
makeinfo --no-split -o packaging/info/casmgr-server.info packaging/info/casmgr-server.texi
echo "Wrote packaging/info/casmgr-server.info"
