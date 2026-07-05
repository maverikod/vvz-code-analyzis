#!/usr/bin/env bash
# Shared runtime for casmgr / casmgr-config launchers.
#
# The casmgr-server package ships no host Python venv and no copy of the
# code_analysis package: the daemon, its CLI, and PostgreSQL all run inside
# the single "casmgr" Docker container (see packaging/systemd/casmgr.service,
# /etc/casmgr/docker-compose.yml). These helpers dispatch host commands into
# that container via `docker exec` / `systemctl` and never resolve a local
# Python interpreter.
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

CASMGR_CONTAINER="${CASMGR_CONTAINER:-casmgr}"
CASMGR_VENV_PYTHON="${CASMGR_VENV_PYTHON:-/opt/casmgr/venv/bin/python}"
CASMGR_CONFIG="${CASMGR_CONFIG:-/etc/casmgr/config.json}"

casmgr_container_running() {
    [[ "$(docker inspect -f '{{.State.Running}}' "$CASMGR_CONTAINER" 2>/dev/null)" == "true" ]]
}

casmgr_require_container_running() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "ERROR: docker not found" >&2
        return 1
    fi
    if ! casmgr_container_running; then
        echo "ERROR: ${CASMGR_CONTAINER} container is not running." >&2
        echo "       Start it with: sudo systemctl start casmgr.service" >&2
        return 1
    fi
    return 0
}

casmgr_docker_exec_python() {
    casmgr_require_container_running || return 1
    docker exec "$CASMGR_CONTAINER" "$CASMGR_VENV_PYTHON" "$@"
}

casmgr_exec_config_cli() {
    casmgr_docker_exec_python -m code_analysis.cli.config_cli "$@"
}

casmgr_exec_server_manager_subcommand() {
    # Diagnostic subcommands that still need the running daemon + DB
    # (sessions, locks). start/stop/restart/status/logs are handled by
    # _casmgr_server_entry() directly via systemctl/docker, not this function.
    casmgr_docker_exec_python -m code_analysis.cli.server_manager_cli "$@"
}

casmgr_service_action() {
    systemctl "$1" casmgr.service
}

casmgr_logs() {
    docker logs -f "$CASMGR_CONTAINER"
}

casmgr_init_from_script() {
    # Compatibility no-op for scripts (e.g. casmgr-config-validate) that call
    # this before dispatching; nothing to initialize since code_analysis
    # commands now run via `docker exec` at call time.
    return 0
}
