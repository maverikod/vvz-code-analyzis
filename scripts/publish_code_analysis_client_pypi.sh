#!/bin/bash
#
# Build and upload the code-analysis-client wheel/sdist to PyPI.
# Version is synced from the repository root pyproject.toml first.
#
# Usage:
#   ./scripts/publish_code_analysis_client_pypi.sh
#   ./scripts/publish_code_analysis_client_pypi.sh --check-only
#
# Credentials (non-interactive upload):
#   TWINE_USERNAME=__token__
#   TWINE_PASSWORD=<PyPI API token>
#
# Skip upload (build + twine check only):
#   CASMGR_PYPI_CHECK_ONLY=1
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck source=casmgr_ensure_build_deps.sh
source "${ROOT}/scripts/casmgr_ensure_build_deps.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

error() { echo -e "${RED}ERROR:${NC} $1" >&2; exit 1; }
info() { echo -e "${GREEN}INFO:${NC} $1"; }
warn() { echo -e "${YELLOW}WARN:${NC} $1"; }

CHECK_ONLY=0
if [[ "${1:-}" == "--check-only" ]]; then
    CHECK_ONLY=1
fi
if [[ "${CASMGR_PYPI_CHECK_ONLY:-}" == "1" ]]; then
    CHECK_ONLY=1
fi

if [[ ! -f "${ROOT}/client/pyproject.toml" ]]; then
    error "client/pyproject.toml not found under ${ROOT}"
fi

info "Client version from pyproject.toml"
python3 "${ROOT}/scripts/sync_dependency_versions.py" --repo-root "${ROOT}"
python3 "${ROOT}/scripts/sync_code_analysis_client_version.py" --repo-root "${ROOT}"

CLIENT_VERSION="$(casmgr_read_project_version "${ROOT}")"
info "Publishing code-analysis-client ${CLIENT_VERSION}"

python3 -m pip install --upgrade pip build twine >/dev/null

rm -rf "${ROOT}/client/dist" "${ROOT}/client/build" \
    "${ROOT}/client/"*.egg-info 2>/dev/null || true

(
    cd "${ROOT}/client"
    python3 -m build
)

info "twine check"
python3 -m twine check "${ROOT}/client/dist/"*

if (( CHECK_ONLY )); then
    info "Check-only mode; skipping twine upload"
    exit 0
fi

if [[ -z "${TWINE_USERNAME:-}" || -z "${TWINE_PASSWORD:-}" ]]; then
    error "TWINE_USERNAME and TWINE_PASSWORD must be set for PyPI upload (use __token__ + API token). For build-only: --check-only"
fi

info "Uploading to PyPI: code-analysis-client ${CLIENT_VERSION}"
python3 -m twine upload "${ROOT}/client/dist/"*
info "PyPI upload complete: code-analysis-client ${CLIENT_VERSION}"
