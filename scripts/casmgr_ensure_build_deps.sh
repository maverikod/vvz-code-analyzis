#!/bin/bash
# Ensure system (non-pip) dependencies for casmgr-server build and runtime.
# Installs missing Debian packages via sudo apt-get when possible.
#
# Usage:
#   source scripts/casmgr_ensure_build_deps.sh
#   casmgr_ensure_build_deps --deb [--docker]
#
#   ./scripts/casmgr_ensure_build_deps.sh --deb --docker
#
# Environment:
#   CASMGR_SKIP_BUILD_DEPS=1  — do not run apt/sudo (fail if tools missing)
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    set -euo pipefail
fi

_casmgr_deps_red='\033[0;31m'
_casmgr_deps_green='\033[0;32m'
_casmgr_deps_yellow='\033[1;33m'
_casmgr_deps_nc='\033[0m'

_casmgr_deps_info() { echo -e "${_casmgr_deps_green}INFO:${_casmgr_deps_nc} $1"; }
_casmgr_deps_warn() { echo -e "${_casmgr_deps_yellow}WARN:${_casmgr_deps_nc} $1"; }
_casmgr_deps_error() { echo -e "${_casmgr_deps_red}ERROR:${_casmgr_deps_nc} $1" >&2; exit 1; }

# Apt packages (everything that is NOT installed via pip into the app venv).
# Keep in sync with debian/control Depends/Recommends where applicable.
readonly CASMGR_APT_PYTHON=(python3 python3-venv python3-pip)
readonly CASMGR_APT_RUNTIME=(
    openssl
    ca-certificates
    adduser
    rsync
    postgresql-client
    systemd
)
readonly CASMGR_APT_DEB_BUILD=(devscripts debhelper texinfo)
readonly CASMGR_APT_DOCKER=(docker.io)

# Read project version from pyproject.toml (no Python required).
casmgr_read_project_version() {
    local root="${1:-.}"
    local file="${root}/pyproject.toml"
    if [[ ! -f "$file" ]]; then
        _casmgr_deps_error "pyproject.toml not found under ${root}"
    fi
    local ver
    ver="$(grep -E '^version = "' "$file" | head -1 | sed -n 's/^version = "\([^"]*\)".*/\1/p')"
    if [[ -z "$ver" ]]; then
        _casmgr_deps_error "could not read version from ${file}"
    fi
    echo "$ver"
}

_casmgr_pkg_installed() {
    local pkg="$1"
    dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed"
}

_casmgr_any_pkg_installed() {
    local pkg
    for pkg in "$@"; do
        if _casmgr_pkg_installed "$pkg"; then
            return 0
        fi
    done
    return 1
}

_casmgr_sudo() {
    if [[ "${CASMGR_SKIP_BUILD_DEPS:-}" == "1" ]]; then
        _casmgr_deps_error "missing dependency and CASMGR_SKIP_BUILD_DEPS=1"
    fi
    if ! command -v sudo >/dev/null 2>&1; then
        _casmgr_deps_error "sudo not found; install dependencies manually"
    fi
    if ! sudo -n true 2>/dev/null; then
        _casmgr_deps_info "sudo may prompt for your password to install packages"
    fi
    sudo "$@"
}

_casmgr_apt_install() {
    local missing=("$@")
    if (( ${#missing[@]} == 0 )); then
        return 0
    fi
    if [[ ! -f /etc/debian_version ]]; then
        _casmgr_deps_error \
            "auto-install supports Debian/Ubuntu only; install manually: ${missing[*]}"
    fi
    _casmgr_deps_info "Installing packages: ${missing[*]}"
    _casmgr_sudo apt-get update -qq
    _casmgr_sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}"
}

_casmgr_dedupe_array() {
    local -n _src="$1"
    local -n _dst="$2"
    _dst=()
    local seen="" item
    for item in "${_src[@]}"; do
        if [[ " ${seen} " != *" ${item} "* ]]; then
            _dst+=("$item")
            seen+=" ${item}"
        fi
    done
}

_casmgr_require_cmds() {
    local cmd
    for cmd in "$@"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            case "$cmd" in
                pg_isready)
                    _casmgr_deps_error \
                        "${cmd} not found (install: sudo apt-get install postgresql-client)"
                    ;;
                *)
                    _casmgr_deps_error "required command not found: ${cmd}"
                    ;;
            esac
        fi
    done
}

_casmgr_verify_python_version() {
    python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit(
        f"python3 >= 3.10 required, got {sys.version_info.major}.{sys.version_info.minor}"
    )
PY
}

_casmgr_verify_pip_module() {
    python3 -m pip --version >/dev/null 2>&1 || \
        _casmgr_deps_error "python3 -m pip failed (install python3-pip)"
}

_casmgr_verify_venv_works() {
    local tmp
    tmp="$(mktemp -d "${TMPDIR:-/tmp}/casmgr-venv-check.XXXXXX")"
    if ! python3 -m venv "${tmp}/venv" >/dev/null 2>&1; then
        rm -rf "$tmp"
        _casmgr_deps_error \
            "python3 -m venv failed (install python3-venv / python3.*-venv)"
    fi
    if [[ ! -x "${tmp}/venv/bin/python" || ! -x "${tmp}/venv/bin/pip" ]]; then
        rm -rf "$tmp"
        _casmgr_deps_error "venv created but bin/python or bin/pip missing"
    fi
    if ! "${tmp}/venv/bin/pip" install --upgrade pip >/dev/null 2>&1; then
        rm -rf "$tmp"
        _casmgr_deps_error "pip inside venv failed (check python3-pip / network / ca-certificates)"
    fi
    rm -rf "$tmp"
}

_casmgr_verify_runtime_stack() {
    _casmgr_deps_info "Verifying Python runtime (>= 3.10, venv, pip) ..."
    _casmgr_require_cmds python3
    _casmgr_verify_python_version
    _casmgr_verify_pip_module
    _casmgr_verify_venv_works
    _casmgr_deps_info "Python runtime OK"
}

_casmgr_verify_runtime_commands() {
    _casmgr_deps_info "Verifying runtime commands ..."
    _casmgr_require_cmds openssl rsync addgroup adduser systemctl pg_isready
    # postinst / admin scripts
    _casmgr_require_cmds install chown chmod sed grep getent
    _casmgr_deps_info "Runtime commands OK"
}

_casmgr_verify_deb_build_commands() {
    _casmgr_deps_info "Verifying Debian build tools ..."
    _casmgr_require_cmds dpkg-buildpackage dh dpkg-deb
    if command -v makeinfo >/dev/null 2>&1; then
        :
    else
        local root="${CASMGR_ROOT:-}"
        if [[ -z "$root" ]]; then
            root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
        fi
        if [[ ! -f "${root}/packaging/info/casmgr-server.info" ]]; then
            _casmgr_deps_error \
                "makeinfo not found and no prebuilt packaging/info/casmgr-server.info"
        fi
        _casmgr_deps_warn "makeinfo missing; deb build will use prebuilt .info file"
    fi
    _casmgr_deps_info "Debian build tools OK"
}

_casmgr_verify_docker() {
    _casmgr_deps_info "Verifying Docker ..."
    _casmgr_require_cmds docker
    if ! docker info >/dev/null 2>&1; then
        _casmgr_deps_warn \
            "docker CLI present but daemon not reachable; use sudo docker or add user to group docker"
    else
        _casmgr_deps_info "Docker OK"
    fi
}

# casmgr_ensure_build_deps [--deb] [--runtime] [--docker] [--info]
# --deb implies --runtime (platform deps are always checked for deb workflows).
casmgr_ensure_build_deps() {
    local want_deb=0 want_runtime=0 want_docker=0 want_info=0
    if (($# == 0)); then
        want_deb=1
    fi
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --deb) want_deb=1 ;;
            --runtime) want_runtime=1 ;;
            --docker) want_docker=1 ;;
            --info) want_info=1 ;;
            -h|--help)
                cat <<'EOF'
Usage: casmgr_ensure_build_deps [--deb] [--runtime] [--docker] [--info]

Installs and verifies system (non-pip) dependencies on Debian/Ubuntu.

  --deb       devscripts, debhelper, texinfo + build tool checks
  --runtime   python3, python3-venv, python3-pip, openssl, ca-certificates,
              adduser, rsync, postgresql-client; functional venv/pip test
              (enabled automatically with --deb)
  --docker    docker.io (or existing docker-ce) + docker info check
  --info      texinfo only (makeinfo)

Set CASMGR_SKIP_BUILD_DEPS=1 to disable apt/sudo auto-install.

Pip packages from pyproject.toml are installed into /usr/lib/casmgr-server/.venv
at package postinst, not by this script.
EOF
                return 0
                ;;
            *) _casmgr_deps_error "unknown option: $1" ;;
        esac
        shift
    done

    if (( want_deb )); then
        want_runtime=1
    fi

    local to_install=() seen=""
    local pkg

    # Nested helpers mutate to_install in this shell (no command-substitution subshells).
    _queue_pkg() {
        local pkg="$1"
        local force="${2:-0}"
        if [[ " ${seen} " == *" ${pkg} "* ]]; then
            return 0
        fi
        if (( force == 0 )) && _casmgr_pkg_installed "$pkg"; then
            return 0
        fi
        to_install+=("$pkg")
        seen+=" ${pkg}"
    }

    _queue_for_cmd() {
        local cmd="$1"
        shift
        if command -v "$cmd" >/dev/null 2>&1; then
            return 0
        fi
        local pkg
        for pkg in "$@"; do
            _queue_pkg "$pkg" 1
        done
    }

    if (( want_runtime )); then
        for pkg in "${CASMGR_APT_RUNTIME[@]}"; do
            _queue_pkg "$pkg"
        done
        _queue_for_cmd pg_isready postgresql-client postgresql-client-common
        _queue_for_cmd openssl openssl
        _queue_for_cmd rsync rsync
        _queue_for_cmd addgroup adduser
        _queue_for_cmd adduser adduser
        _queue_for_cmd systemctl systemd
    fi

    if (( want_runtime || want_info || want_deb )); then
        if ! command -v python3 >/dev/null 2>&1; then
            _queue_pkg python3 1
        fi
        if ! python3 -m pip --version >/dev/null 2>&1; then
            for pkg in "${CASMGR_APT_PYTHON[@]}"; do
                _queue_pkg "$pkg" 1
            done
        fi
        if ! python3 -m venv --help >/dev/null 2>&1; then
            _queue_pkg python3-venv 1
        fi
    fi

    if (( want_deb || want_info )); then
        for pkg in "${CASMGR_APT_DEB_BUILD[@]}"; do
            if [[ "$pkg" == "texinfo" ]] && command -v makeinfo >/dev/null 2>&1; then
                continue
            fi
            _queue_pkg "$pkg"
        done
        if (( want_deb )); then
            _queue_for_cmd dpkg-buildpackage devscripts
            _queue_for_cmd dh debhelper
            _queue_for_cmd dpkg-deb dpkg-dev
        fi
        if (( want_info || want_deb )) && ! command -v makeinfo >/dev/null 2>&1; then
            _queue_pkg texinfo 1
        fi
    fi

    if (( want_docker )); then
        if ! command -v docker >/dev/null 2>&1; then
            if ! _casmgr_any_pkg_installed docker.io docker-ce docker-ce-cli moby-engine; then
                _queue_pkg docker.io
            fi
        fi
    fi

    local deduped=()
    _casmgr_dedupe_array to_install deduped
    _casmgr_apt_install "${deduped[@]}"

    if (( want_runtime )); then
        _casmgr_verify_runtime_stack
        _casmgr_verify_runtime_commands
    elif (( want_deb || want_info )); then
        _casmgr_require_cmds python3
        _casmgr_verify_python_version
    fi

    if (( want_deb )); then
        _casmgr_verify_deb_build_commands
    fi

    if (( want_info )); then
        _casmgr_require_cmds makeinfo
    fi

    if (( want_docker )); then
        _casmgr_verify_docker
    fi

    _casmgr_deps_info "All requested system dependencies OK"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    casmgr_ensure_build_deps "$@"
fi
