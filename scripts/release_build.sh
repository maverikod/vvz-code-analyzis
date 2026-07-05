#!/bin/bash
#
# Release pipeline: build & push the single casmgr Docker image (from
# docker/casmgr/Dockerfile), Debian package, and (on full release) publish
# code-analysis-client to PyPI.
# Version: root pyproject.toml; Docker tag and client wheel use the same value.
#
# Usage (after git clone):
#   ./build.sh                    # deb only, version from pyproject.toml
#   ./scripts/release_build.sh --deb-only
#   ./scripts/release_build.sh 1.6.35              # full release with explicit version
#   ./scripts/release_build.sh 1.6.35 --deb-only
#   ./scripts/release_build.sh 1.6.35 --skip-pypi   # Docker + deb, no PyPI
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

error() { echo -e "${RED}ERROR:${NC} $1" >&2; exit 1; }
info() { echo -e "${GREEN}INFO:${NC} $1"; }
warn() { echo -e "${YELLOW}WARN:${NC} $1"; }

VERSION=""
CLI_VERSION=""
DO_DOCKER=1
DO_DEB=1
FORCE_PYPI=0
SKIP_PYPI=0
SKIP_DOCKER_PUSH=0
SKIP_DEPS=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --deb-only) DO_DOCKER=0 ;;
        --docker-only) DO_DEB=0 ;;
        --pypi) FORCE_PYPI=1 ;;
        --skip-pypi) SKIP_PYPI=1 ;;
        --skip-docker-push) SKIP_DOCKER_PUSH=1 ;;
        --skip-deps) SKIP_DEPS=1 ;;
        -h|--help)
            cat <<'EOF'
Usage: release_build.sh [VERSION] [--deb-only|--docker-only] [--pypi|--skip-pypi] [--skip-docker-push] [--skip-deps]

  VERSION       Optional; default is version from pyproject.toml
  --deb-only    Build Debian package only (still ensures Docker Hub tag unless --skip-docker-push)
  --docker-only Build and push Docker image only (PyPI upload at end by default)
  --pypi        Publish code-analysis-client to PyPI after build (also with --deb-only)
  --skip-pypi   Skip PyPI upload even on full Docker release
  --skip-docker-push  Build deb without publishing or verifying Docker Hub image (local dev only)
  --skip-deps   Do not auto-install build packages (CASMGR_SKIP_BUILD_DEPS=1)

PyPI upload requires TWINE_USERNAME and TWINE_PASSWORD (e.g. __token__ + API token).

After git clone, run from repository root:

  ./build.sh

Full release (Docker push + deb + PyPI client):

  ./scripts/release_build.sh

EOF
            exit 0
            ;;
        -*)
            error "Unknown option: $1"
            ;;
        *)
            if [[ -n "$VERSION" ]]; then
                error "Unexpected argument: $1"
            fi
            VERSION="$1"
            CLI_VERSION="$1"
            ;;
    esac
    shift
done

export CASMGR_ROOT="$ROOT"

# shellcheck source=casmgr_ensure_build_deps.sh
source "${ROOT}/scripts/casmgr_ensure_build_deps.sh"

if [[ -z "$VERSION" ]]; then
    VERSION="$(casmgr_read_project_version "$ROOT")"
    info "Using version ${VERSION} from pyproject.toml"
fi

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.+~]+)?$ ]]; then
    error "VERSION must look like a semver release tag (got: ${VERSION})"
fi

# Full Docker release publishes the client wheel unless explicitly skipped.
DO_PYPI=0
if (( FORCE_PYPI )) || { (( DO_DOCKER )) && (( ! SKIP_PYPI )); }; then
    if [[ "${CASMGR_SKIP_PYPI:-}" != "1" ]]; then
        DO_PYPI=1
    fi
fi
if [[ "${CASMGR_PUBLISH_PYPI:-}" == "1" ]]; then
    DO_PYPI=1
fi
if [[ "${CASMGR_SKIP_PYPI:-}" == "1" ]] || (( SKIP_PYPI )); then
    DO_PYPI=0
fi

casmgr_write_pyproject_version() {
    python3 - <<PY
import re
from pathlib import Path
version = "${VERSION}"
path = Path("pyproject.toml")
text = path.read_text(encoding="utf-8")
text, n = re.subn(r'(?m)^version = "[^"]+"', f'version = "{version}"', text, count=1)
if n != 1:
    raise SystemExit("could not update version in pyproject.toml")
path.write_text(text, encoding="utf-8")
PY
}

casmgr_sync_client_version_from_pyproject() {
    python3 "${ROOT}/scripts/sync_code_analysis_client_version.py" --repo-root "${ROOT}"
}

REGISTRY="${CASMGR_DOCKER_REGISTRY:-vasilyvz}"
IMAGE_NAME="${CASMGR_DOCKER_IMAGE_NAME:-casmgr}"
FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${VERSION}"
LATEST_IMAGE="${REGISTRY}/${IMAGE_NAME}:latest"
DEB_VERSION="${VERSION}-1"

export CASMGR_RELEASE_VERSION="$VERSION"
export CASMGR_RELEASE_IMAGE="$FULL_IMAGE"

if (( SKIP_DEPS )); then
    export CASMGR_SKIP_BUILD_DEPS=1
fi

deps_args=()
(( DO_DEB )) && deps_args+=(--deb)
if (( DO_DOCKER )) || { (( DO_DEB )) && (( ! SKIP_DOCKER_PUSH )); }; then
    deps_args+=(--docker)
fi
if (( ${#deps_args[@]} == 0 )); then
    deps_args=(--deb)
fi
casmgr_ensure_build_deps "${deps_args[@]}"

if [[ -n "$CLI_VERSION" ]]; then
    info "Writing version ${VERSION} to pyproject.toml"
    casmgr_write_pyproject_version
fi
casmgr_sync_client_version_from_pyproject

casmgr_docker_image_on_hub() {
    local ref="$1"
    local hub_name="${2:-${IMAGE_NAME}}"
    if command -v docker >/dev/null 2>&1; then
        if docker manifest inspect "$ref" >/dev/null 2>&1; then
            return 0
        fi
    fi
    if command -v curl >/dev/null 2>&1; then
        if curl -fsS \
            "https://hub.docker.com/v2/repositories/${REGISTRY}/${hub_name}/tags/${VERSION}/" \
            >/dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

casmgr_verify_docker_image_on_hub() {
    local ref="$1"
    local hub_name="${2:-${IMAGE_NAME}}"
    if casmgr_docker_image_on_hub "$ref" "$hub_name"; then
        info "Verified on Docker Hub: ${ref}"
        return 0
    fi
    error "Docker Hub verification failed: ${ref} not found after push"
}

casmgr_build_and_push_docker_image() {
    info "Building Docker image ${FULL_IMAGE}"
    docker build \
        -f docker/casmgr/Dockerfile \
        --build-arg VERSION="${VERSION}" \
        -t "${FULL_IMAGE}" \
        -t "${LATEST_IMAGE}" \
        .
    info "Pushing ${FULL_IMAGE}"
    docker push "${FULL_IMAGE}"
    info "Pushing ${LATEST_IMAGE}"
    docker push "${LATEST_IMAGE}"
    casmgr_verify_docker_image_on_hub "${FULL_IMAGE}"
}

casmgr_ensure_docker_image_published() {
    if casmgr_docker_image_on_hub "${FULL_IMAGE}"; then
        info "Docker Hub already has ${FULL_IMAGE}"
        return 0
    fi
    warn "Image ${FULL_IMAGE} is not on Docker Hub yet; building and pushing"
    casmgr_build_and_push_docker_image
}

if (( DO_DOCKER )); then
    casmgr_build_and_push_docker_image
elif (( DO_DEB )) && (( ! SKIP_DOCKER_PUSH )); then
    casmgr_ensure_docker_image_published
fi

echo "${FULL_IMAGE}" > debian/casmgr-docker-image
info "Recorded image ref in debian/casmgr-docker-image"

DEBIAN_DATE="$(date -R)"
cat > debian/changelog <<EOF
casmgr-server (${DEB_VERSION}) unstable; urgency=medium

  * Release ${VERSION} — Docker image ${FULL_IMAGE}

 -- Vasiliy Zdanovskiy <vasilyvz@gmail.com>  ${DEBIAN_DATE}

EOF

casmgr_clean_source_for_debian_build() {
    local root="$1"
    info "Cleaning Python artifacts before dpkg-buildpackage ..."
    rm -rf "${root}/debian/casmgr-server" "${root}/debian/files" 2>/dev/null || true

    local need_sudo=0
    local dir
    while IFS= read -r dir; do
        [[ -n "$dir" ]] || continue
        if ! rm -rf "$dir" 2>/dev/null; then
            need_sudo=1
        fi
    done < <(
        find "$root" \
            \( -path "${root}/.git" -o -path "${root}/.venv" -o -path "${root}/venv" \) -prune \
            -o -type d -name __pycache__ -print 2>/dev/null
    )

    if (( need_sudo )); then
        warn "Some __pycache__ dirs are not writable (often root-owned after 'sudo' runs)"
        if command -v sudo >/dev/null 2>&1; then
            info "Retrying __pycache__ cleanup with sudo ..."
            while IFS= read -r dir; do
                [[ -n "$dir" ]] || continue
                sudo rm -rf "$dir" 2>/dev/null || true
            done < <(
                find "$root" \
                    \( -path "${root}/.git" -o -path "${root}/.venv" -o -path "${root}/venv" \) -prune \
                    -o -type d -name __pycache__ -print 2>/dev/null
            )
        else
            error "Remove root-owned __pycache__, then rebuild: sudo rm -rf code_analysis/**/__pycache__"
        fi
    fi

    while IFS= read -r f; do
        [[ -n "$f" ]] || continue
        rm -f "$f" 2>/dev/null || sudo rm -f "$f" 2>/dev/null || true
    done < <(
        find "$root" \
            \( -path "${root}/.git" -o -path "${root}/.venv" -o -path "${root}/venv" \) -prune \
            -o -type f \( -name '*.pyc' -o -name '*.pyo' \) -print 2>/dev/null
    )
}

if (( DO_DEB )); then
    if (( ! SKIP_DOCKER_PUSH )) && ! casmgr_docker_image_on_hub "${FULL_IMAGE}"; then
        error "Refusing to build deb: ${FULL_IMAGE} is not on Docker Hub (run without --skip-docker-push)"
    fi
    info "Checking packaging/config.json.template before deb build"
    if [[ ! -f "${ROOT}/packaging/config.json.template" ]]; then
        error "packaging/config.json.template missing"
    fi
    if [[ -x "${ROOT}/.venv/bin/python" ]]; then
        "${ROOT}/.venv/bin/python" -m pytest \
            "${ROOT}/tests/test_packaging_config_template.py" -q \
            || error "packaging config template checks failed"
    else
        warn "No .venv; skipping packaging config template pytest (run tests manually)"
    fi
    casmgr_clean_source_for_debian_build "$ROOT"
    info "Building Debian package casmgr-server_${DEB_VERSION}_all.deb"
    rm -rf debian/casmgr-server debian/files ../casmgr-server_*.deb ../casmgr-server_*.changes 2>/dev/null || true
    dpkg-buildpackage -us -uc -b
    DEB_FILE="$(ls -t ../casmgr-server_*.deb 2>/dev/null | head -1 || true)"
    if [[ -n "$DEB_FILE" ]]; then
        info "Built ${DEB_FILE}"
        info "Install: sudo dpkg -i ${DEB_FILE} && sudo apt-get install -f"
        info "Image tag locked to package version: ${FULL_IMAGE}"
    fi
fi

if (( DO_PYPI )); then
    info "Publishing code-analysis-client to PyPI"
    bash "${ROOT}/scripts/publish_code_analysis_client_pypi.sh"
fi

info "Done."
