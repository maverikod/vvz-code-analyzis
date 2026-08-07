#!/bin/bash
#
# Build and upload the code-analysis-client wheel/sdist to PyPI.
# Version is synced from the repository root pyproject.toml first.
#
# Usage:
#   ./scripts/publish_code_analysis_client_pypi.sh
#   ./scripts/publish_code_analysis_client_pypi.sh --check-only
#
# Credentials (non-interactive upload): either
#   TWINE_USERNAME=__token__ + TWINE_PASSWORD=<PyPI API token>, or
#   a ~/.pypirc holding the token (twine reads it itself).
#
# Skip upload (build + twine check only):
#   CASMGR_PYPI_CHECK_ONLY=1
#
# Interpreter: the repository venv (.venv), resolved by absolute path and
# created on demand. This script never installs into the ambient python3:
# on a PEP 668 "externally managed" system interpreter that install is
# refused outright, which used to fail the publish step of a full release
# whenever the caller had not activated the venv first. Which interpreter
# runs the build must not depend on the caller's shell.
#   Override with CASMGR_VENV=/path/to/venv.
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

VENV_DIR="${CASMGR_VENV:-${ROOT}/.venv}"
VENV_PY="${VENV_DIR}/bin/python"

if [[ ! -x "$VENV_PY" ]]; then
    info "Creating build venv at ${VENV_DIR}"
    python3 -m venv "$VENV_DIR" \
        || error "could not create a venv at ${VENV_DIR}; install python3-venv or set CASMGR_VENV to an existing venv"
fi

# Idempotent and offline-friendly: only reached when a tool is missing, so a
# venv that already carries build+twine needs no network at release time.
if ! "$VENV_PY" -c "import build, twine" >/dev/null 2>&1; then
    info "Installing build tooling into ${VENV_DIR}"
    "$VENV_PY" -m pip install --upgrade pip build twine >/dev/null \
        || error "could not install build/twine into ${VENV_DIR}"
fi

info "Client version from pyproject.toml"
"$VENV_PY" "${ROOT}/scripts/sync_dependency_versions.py" --repo-root "${ROOT}"
"$VENV_PY" "${ROOT}/scripts/sync_code_analysis_client_version.py" --repo-root "${ROOT}"

CLIENT_VERSION="$(casmgr_read_project_version "${ROOT}")"
info "Publishing code-analysis-client ${CLIENT_VERSION} using ${VENV_PY}"

rm -rf "${ROOT}/client/dist" "${ROOT}/client/build" \
    "${ROOT}/client/"*.egg-info 2>/dev/null || true

(
    cd "${ROOT}/client"
    "$VENV_PY" -m build
)

info "twine check"
"$VENV_PY" -m twine check "${ROOT}/client/dist/"*

if (( CHECK_ONLY )); then
    info "Check-only mode; skipping twine upload"
    exit 0
fi

# twine reads ~/.pypirc on its own, so env credentials are one valid source,
# not the only one: demanding them refused an already-configured machine.
if [[ -z "${TWINE_USERNAME:-}" || -z "${TWINE_PASSWORD:-}" ]]; then
    if [[ ! -f "${HOME}/.pypirc" ]]; then
        error "no PyPI credentials: set TWINE_USERNAME/TWINE_PASSWORD (__token__ + API token) or provide ~/.pypirc. For build-only: --check-only"
    fi
    info "Using credentials from ${HOME}/.pypirc"
fi

info "Uploading to PyPI: code-analysis-client ${CLIENT_VERSION}"
"$VENV_PY" -m twine upload "${ROOT}/client/dist/"*
info "PyPI upload complete: code-analysis-client ${CLIENT_VERSION}"
