#!/usr/bin/env bash
# Shared runtime for casmgr / casmgr-config launchers (dev checkout and casmgr-server package).
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

# shellcheck disable=SC2034
CASMGR_SERVER_INSTALL="${CASMGR_SERVER_INSTALL:-/usr/lib/casmgr-server}"

_casmgr_realpath() {
    local p="$1"
    if command -v readlink >/dev/null 2>&1; then
        readlink -f "$p" 2>/dev/null || readlink "$p" 2>/dev/null || echo "$p"
    else
        echo "$p"
    fi
}

_casmgr_has_code_analysis() {
    [[ -f "$1/code_analysis/cli/config_cli.py" ]]
}

casmgr_resolve_install_root() {
    local script="$1"
    local dir
    dir="$(cd "$(dirname "$script")" && pwd)"

    case "$dir" in
        /usr/bin)
            if _casmgr_has_code_analysis "$CASMGR_SERVER_INSTALL"; then
                echo "$CASMGR_SERVER_INSTALL"
                return 0
            fi
            ;;
        "${CASMGR_SERVER_INSTALL}/scripts")
            if _casmgr_has_code_analysis "$CASMGR_SERVER_INSTALL"; then
                echo "$CASMGR_SERVER_INSTALL"
                return 0
            fi
            ;;
    esac

    local cur="$dir"
    while [[ "$cur" != "/" ]]; do
        if _casmgr_has_code_analysis "$cur"; then
            echo "$cur"
            return 0
        fi
        cur="$(dirname "$cur")"
    done

    echo "ERROR: code-analysis install root not found (expected code_analysis/ package tree)" >&2
    return 1
}

casmgr_is_production_root() {
    [[ "$1" == "$CASMGR_SERVER_INSTALL" ]]
}

casmgr_ensure_venv() {
    local root="$1"
    local venv="${root}/.venv"
    local py="${venv}/bin/python"
    local pip="${venv}/bin/pip"

    if [[ "${CASMGR_SKIP_BOOTSTRAP:-0}" == "1" ]]; then
        return 0
    fi

    if casmgr_is_production_root "$root"; then
        if [[ ! -x "$py" ]]; then
            echo "ERROR: package venv missing at ${venv}" >&2
            echo "       Reinstall or reconfigure: sudo dpkg-reconfigure casmgr-server" >&2
            return 1
        fi
        return 0
    fi

    if [[ ! -f "${root}/pyproject.toml" ]]; then
        echo "ERROR: ${root}/pyproject.toml not found; cannot bootstrap Python environment" >&2
        return 1
    fi

    local lock_dir="${venv}/.bootstrap.lock"
    if ! mkdir "$lock_dir" 2>/dev/null; then
        local waited=0
        while [[ ! -x "$py" ]] && [[ $waited -lt 600 ]]; do
            sleep 2
            waited=$((waited + 2))
        done
        if [[ -x "$py" ]] && "$py" -c "import code_analysis" >/dev/null 2>&1; then
            return 0
        fi
        echo "ERROR: timed out waiting for venv bootstrap in ${venv}" >&2
        return 1
    fi

    trap 'rmdir "$lock_dir" 2>/dev/null || true' EXIT

    if [[ ! -x "$py" ]]; then
        echo "Setting up Python environment in ${venv} ..." >&2
        if ! python3 -m venv "$venv"; then
            rmdir "$lock_dir" 2>/dev/null || true
            echo "ERROR: python3 -m venv failed (install python3-venv / python3.*-venv)" >&2
            return 1
        fi
        "$pip" install --upgrade pip setuptools wheel
    fi

    if ! "$py" -c "import code_analysis" >/dev/null 2>&1; then
        echo "Installing code-analysis dependencies (editable) ..." >&2
        "$pip" install -e "$root"
    fi

    rmdir "$lock_dir" 2>/dev/null || true
    trap - EXIT
    return 0
}

casmgr_resolve_python() {
    local root="$1"

    if [[ -n "${CASMGR_PYTHON:-}" ]]; then
        if [[ -x "$CASMGR_PYTHON" ]]; then
            echo "$CASMGR_PYTHON"
            return 0
        fi
        echo "ERROR: CASMGR_PYTHON is set but not executable: ${CASMGR_PYTHON}" >&2
        return 1
    fi

    local cand
    for cand in \
        "${root}/.venv/bin/python" \
        "${root}/venv/bin/python" \
        "${CASMGR_SERVER_INSTALL}/.venv/bin/python"
    do
        if [[ -x "$cand" ]]; then
            echo "$cand"
            return 0
        fi
    done

    if casmgr_is_production_root "$root"; then
        echo "ERROR: Python venv not found under ${root}/.venv (broken casmgr-server install)" >&2
        return 1
    fi

    echo "ERROR: Python venv not found under ${root}/.venv after bootstrap" >&2
    return 1
}

casmgr_prepare_runtime() {
    local script="$1"
    local script_real
    script_real="$(_casmgr_realpath "$script")"

    CASMGR_INSTALL_ROOT="$(casmgr_resolve_install_root "$script_real")"
    casmgr_ensure_venv "$CASMGR_INSTALL_ROOT"
    CASMGR_PYTHON="$(casmgr_resolve_python "$CASMGR_INSTALL_ROOT")"

    cd "$CASMGR_INSTALL_ROOT"
    export PYTHONPATH="${CASMGR_INSTALL_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

    if casmgr_is_production_root "$CASMGR_INSTALL_ROOT"; then
        export CASMGR_LOG="${CASMGR_LOG:-/var/log/casmgr}"
        export CASMGR_CONFIG="${CASMGR_CONFIG:-/etc/casmgr/config.json}"
    fi

    if ! "$CASMGR_PYTHON" -c "import code_analysis" >/dev/null 2>&1; then
        echo "ERROR: cannot import code_analysis (root=${CASMGR_INSTALL_ROOT}, python=${CASMGR_PYTHON})" >&2
        if casmgr_is_production_root "$CASMGR_INSTALL_ROOT"; then
            echo "       Reinstall package or run: sudo dpkg-reconfigure casmgr-server" >&2
        fi
        return 1
    fi
}

casmgr_exec_config_cli() {
    exec "$CASMGR_PYTHON" -m code_analysis.cli.config_cli "$@"
}

casmgr_exec_server_manager() {
    exec "$CASMGR_PYTHON" -m code_analysis.cli.server_manager_cli "$@"
}

casmgr_init_from_script() {
    casmgr_prepare_runtime "$1"
}
