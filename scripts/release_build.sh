#!/bin/bash
#
# Release pipeline: build & push casmgr-postgres Docker image, then build Debian package.
# Package version and Docker tag match pyproject.toml unless VERSION is passed explicitly.
#
# Usage (after git clone):
#   ./build.sh                    # deb only, version from pyproject.toml
#   ./scripts/release_build.sh --deb-only
#   ./scripts/release_build.sh 1.0.7              # full release with explicit version
#   ./scripts/release_build.sh 1.0.7 --deb-only
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
DO_DOCKER=1
DO_DEB=1
SKIP_DEPS=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --deb-only) DO_DOCKER=0 ;;
        --docker-only) DO_DEB=0 ;;
        --skip-deps) SKIP_DEPS=1 ;;
        -h|--help)
            cat <<'EOF'
Usage: release_build.sh [VERSION] [--deb-only|--docker-only] [--skip-deps]

  VERSION       Optional; default is version from pyproject.toml
  --deb-only    Build Debian package only (no Docker build/push)
  --docker-only Build and push Docker image only
  --skip-deps   Do not auto-install build packages (CASMGR_SKIP_BUILD_DEPS=1)

After git clone, run from repository root:

  ./build.sh

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

REGISTRY="${CASMGR_DOCKER_REGISTRY:-vasilyvz}"
IMAGE_NAME="${CASMGR_DOCKER_IMAGE_NAME:-casmgr-postgres}"
FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${VERSION}"
DEB_VERSION="${VERSION}-1"

export CASMGR_RELEASE_VERSION="$VERSION"
export CASMGR_RELEASE_IMAGE="$FULL_IMAGE"

if (( SKIP_DEPS )); then
    export CASMGR_SKIP_BUILD_DEPS=1
fi

deps_args=()
(( DO_DEB )) && deps_args+=(--deb)
(( DO_DOCKER )) && deps_args+=(--docker)
if (( ${#deps_args[@]} == 0 )); then
    deps_args=(--deb)
fi
casmgr_ensure_build_deps "${deps_args[@]}"

if (( DO_DOCKER )); then
    info "Building Docker image ${FULL_IMAGE}"
    docker build \
        -f docker/casmgr-postgres/Dockerfile \
        --build-arg VERSION="${VERSION}" \
        -t "${FULL_IMAGE}" \
        .
    info "Pushing ${FULL_IMAGE}"
    docker push "${FULL_IMAGE}"
fi

echo "${FULL_IMAGE}" > debian/casmgr-docker-image
info "Recorded image ref in debian/casmgr-docker-image"

info "Syncing Python package version to ${VERSION} in pyproject.toml"
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

DEBIAN_DATE="$(date -R)"
cat > debian/changelog <<EOF
casmgr-server (${DEB_VERSION}) unstable; urgency=medium

  * Release ${VERSION} — Docker image ${FULL_IMAGE}

 -- Vasiliy Zdanovskiy <vasilyvz@gmail.com>  ${DEBIAN_DATE}

EOF

if (( DO_DEB )); then
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

info "Done."
