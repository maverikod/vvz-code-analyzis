#!/usr/bin/env bash
# Entry helper for casmgr CLI scripts (source from casmgr-config, casmgr, etc.).
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

_casmgr_locate_runtime_sh() {
    local script="$1"
    local dir
    dir="$(cd "$(dirname "$script")" && pwd)"

    if [[ -f "${dir}/lib/casmgr-runtime.sh" ]]; then
        echo "${dir}/lib/casmgr-runtime.sh"
        return 0
    fi
    if [[ -f "/usr/lib/casmgr-server/scripts/lib/casmgr-runtime.sh" ]]; then
        echo "/usr/lib/casmgr-server/scripts/lib/casmgr-runtime.sh"
        return 0
    fi

    local cur="$dir"
    while [[ "$cur" != "/" ]]; do
        if [[ -f "${cur}/scripts/lib/casmgr-runtime.sh" ]]; then
            echo "${cur}/scripts/lib/casmgr-runtime.sh"
            return 0
        fi
        cur="$(dirname "$cur")"
    done
    return 1
}

_casmgr_runtime="$(_casmgr_locate_runtime_sh "${BASH_SOURCE[1]}")" || {
    echo "ERROR: casmgr-runtime.sh not found (install casmgr-server or run from repo scripts/)" >&2
    exit 1
}
# shellcheck disable=SC1090
source "$_casmgr_runtime"

casmgr_entry() {
    local script="$1"
    local command="$2"
    shift 2
    case "$command" in
        config)
            casmgr_exec_config_cli "$@"
            ;;
        server)
            _casmgr_server_entry "$@"
            ;;
        *)
            echo "ERROR: unknown casmgr entry command: $command" >&2
            exit 1
            ;;
    esac
}

_casmgr_server_entry() {
    local sub="${1:-status}"
    [[ $# -gt 0 ]] && shift
    case "$sub" in
        start|stop|restart|status)
            casmgr_service_action "$sub"
            ;;
        logs)
            casmgr_logs
            ;;
        sessions|locks)
            casmgr_exec_server_manager_subcommand "$sub" "$@"
            ;;
        *)
            echo "ERROR: unknown casmgr server command: $sub" >&2
            echo "       Supported: start stop restart status logs sessions locks" >&2
            exit 1
            ;;
    esac
}
