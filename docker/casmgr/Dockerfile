# casmgr — all-in-one image: PostgreSQL 16 + pgvector, the code_analysis MCP
# daemon, and all its in-process workers, supervised by s6-overlay v3.
#
# Build (from repo root):
#   docker build -f docker/casmgr/Dockerfile -t vasilyvz/casmgr:VERSION .
#
# Base: ubuntu:24.04 ("noble"). This base's SYSTEM /usr/bin/python3 is CPython
# 3.12, matching the HOST (Ubuntu 24.04) that creates per-project virtualenvs
# bind-mounted into this container under /var/casmgr/watched/<uuid4>. Those
# host-created venvs' bin/python* symlink-chains to /usr/bin/python3; if the
# container's system python3 were a different minor version (as it was on the
# old pgvector/pgvector:pg16 base, Debian bookworm's python3.11), the venv's
# site-packages (including pip itself, installed for 3.12) become invisible
# inside the container, and project_pip_install fails with
# "No module named pip". Keeping container system python3 == host system
# python3 (3.12, real apt package, not a symlink hack) is the fix. The app's
# own venv (/opt/casmgr/venv) is built from this same system python3, dropping
# the previous standalone-interpreter-via-uv approach entirely.
#
# PostgreSQL 16 + pgvector + gosu are NOT part of ubuntu:24.04 (unlike the old
# pgvector/pgvector base, which shipped them out of the box) — installed below
# from the official PGDG apt repo.
#
# Runtime bind mounts (rw, casuser-root on the host):
#   /etc/casmgr       config.json, mtls/, docker-compose.yml
#   /var/casmgr       secrets/.env, postgres/{data,cache}, data/, faiss/, locks/,
#                     backups/, trash/, versions/, watch_catalog/, watched/<uuid4>
#   /var/log/casmgr   daemon logs + postgres/
#
# PID 1 (s6-overlay) stays root for init. The code_analysis daemon
# (code_analysis.main, service 40-casmgr) drops privileges to casuser via gosu
# using CASMGR_UID/CASMGR_GID (the host casuser's real numeric ids, injected at
# runtime via compose `environment`, sourced from /etc/casmgr/.env -- the ENV
# defaults below are local-run fallbacks only). This makes files the daemon
# creates in the bind-mounted watched trees casuser-owned on the host, not
# root:root. PostgreSQL still drops privileges to uid/gid 999 via gosu,
# unchanged from the old base -- see the explicit uid/gid remap RUN step below,
# which forces the PGDG package's "postgres" system user (allocated at an
# arbitrary uid/gid by adduser on this base) to 999:999, because the existing
# PRODUCTION data dir at /var/casmgr/postgres/data is already populated at
# uid/gid 999 on disk. Do NOT reuse uid/gid 999 for casuser -- it already
# belongs to postgres.
#
# s6-overlay v3 service tree: docker/casmgr/s6/s6-rc.d/ (see comments in each
# service's up/run script). Boot order: 00-init-dirs -> 10-pg-initdb ->
# 20-postgres (readiness via notification-fd + pg_isready) -> 30-pg-init ->
# 40-casmgr; 05-init-user (creates casuser, chowns daemon-writable dirs) runs
# in parallel off 00-init-dirs and 40-casmgr waits on both 30-pg-init and
# 05-init-user before gosu'ing into casuser.
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

FROM ubuntu:24.04

ARG VERSION=dev
LABEL org.opencontainers.image.title="casmgr" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.description="All-in-one Code Analysis Server (casmgr): PostgreSQL 16 + pgvector + code_analysis daemon, s6-overlay supervised"

ARG S6_OVERLAY_VERSION=3.2.3.0

# python3/python3-venv/python3-pip: system Python 3.12 on ubuntu:24.04 (see
# header) -- the app venv is built from this. git for project_git commands;
# openssh-client provides the `ssh` binary that git_* remote commands invoke
# via GIT_SSH_COMMAND (git alone is not enough -- without it: "ssh: not
# found"); ca-certificates for TLS/pip; sudo for casuser's on-demand root
# escalation; xz-utils to unpack the s6-overlay tarballs; curl+gnupg are only
# needed to fetch and dearmor the PGDG apt signing key below; locales because
# ubuntu:24.04 ships no generated glibc locales, but existing PostgreSQL data
# dirs created on the old (Debian) base have en_US.utf8 baked into their
# postgresql.conf (lc_messages/monetary/numeric/time) -- without it postgres
# aborts: 'invalid value for parameter "lc_messages": "en_US.utf8"'.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        python3-pip \
        git \
        openssh-client \
        ca-certificates \
        sudo \
        xz-utils \
        curl \
        gnupg \
        locales \
    && sed -i 's/^# *\(en_US.UTF-8 UTF-8\)/\1/' /etc/locale.gen \
    && locale-gen en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

# PostgreSQL 16 + pgvector + gosu from the official PGDG apt repo: this base,
# unlike the old pgvector/pgvector:pg16 image, has none of psql/pg_ctl/gosu/
# pgvector built in.
RUN curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt noble-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-16 \
        postgresql-16-pgvector \
        gosu \
    && rm -rf /var/lib/apt/lists/*

# Force the PGDG package's "postgres" system user to uid/gid 999:999. adduser
# allocates it at whatever uid/gid the OS picks next (empirically observed
# uid=100/gid=103 and uid=101/gid=103 across otherwise-identical builds --
# apt's dynamic system-id allocation is not stable run to run) -- NOT
# guaranteed 999, unlike the old pgvector/pgvector base where "postgres"
# happened to be uid 999 out of the box. The existing PRODUCTION Postgres data
# dir (/var/casmgr/postgres/data, bind-mounted from the host) is already
# populated with real data owned by uid/gid 999 on disk, and the s6 scripts
# (00-init-dirs.sh, 10-pg-initdb.sh) hardcode 999:999 -- so the image's
# postgres account MUST be 999:999, not whatever the package manager assigned.
# gid/uid 999 may already be occupied by some other base-image system account
# (empirically observed: the "systemd-journal" group, pulled in transitively;
# not reproducible in every build) -- detect and relocate any such occupant to
# a clearly-unused high id first (nothing in this container runs journald or
# needs any other system account, so relocating is always safe here).
# usermod -u only renumbers passwd/group entries; it does not chown existing
# files, so any package-created directories owned by the OLD uid/gid must be
# chowned explicitly afterwards.
RUN set -eux; \
    id postgres; \
    if getent group 999 >/dev/null 2>&1 && ! getent group 999 | grep -q '^postgres:'; then \
        occupant_group="$(getent group 999 | cut -d: -f1)"; \
        groupmod -g 59999 "${occupant_group}"; \
    fi; \
    if getent passwd 999 >/dev/null 2>&1 && ! getent passwd 999 | grep -q '^postgres:'; then \
        occupant_user="$(getent passwd 999 | cut -d: -f1)"; \
        usermod -u 59999 "${occupant_user}"; \
    fi; \
    groupmod -g 999 postgres; \
    usermod -u 999 -g 999 postgres; \
    for d in /var/lib/postgresql /var/run/postgresql /var/log/postgresql; do \
        [ -e "${d}" ] && chown -R 999:999 "${d}" || true; \
    done; \
    id postgres | grep -qE '^uid=999\(postgres\) gid=999\(postgres\)'; \
    echo "postgres remapped to 999:999 OK"

# casuser passwordless sudo: on-demand root-escalation path for admin/maintenance
# inside the container. casuser itself is created later, at container RUNTIME,
# by the 05-init-user s6 oneshot (host-injected uid/gid) — this drop-in just
# pre-authorizes the account NAME, which is why we reference it by name, not uid.
# The daemon still runs unprivileged as casuser by default (see 40-casmgr).
COPY docker/casmgr/sudoers.d/casuser /etc/sudoers.d/casuser
RUN chmod 0440 /etc/sudoers.d/casuser \
    && chown root:root /etc/sudoers.d/casuser \
    && visudo -cf /etc/sudoers.d/casuser

# s6-overlay v3 (PID 1 supervisor with dependency-ordered service startup).
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz /tmp/s6-overlay-noarch.tar.xz
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-x86_64.tar.xz /tmp/s6-overlay-x86_64.tar.xz
RUN tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz \
    && tar -C / -Jxpf /tmp/s6-overlay-x86_64.tar.xz \
    && rm -f /tmp/s6-overlay-noarch.tar.xz /tmp/s6-overlay-x86_64.tar.xz

# /usr/lib/postgresql/16/bin (initdb, postgres, pg_ctl, pg_isready, pg_dump,
# psql, pg_restore, ...) is NOT on any default PATH entry -- PGDG's Debian/
# Ubuntu packaging does not symlink these into /usr/bin (confirmed empirically:
# `which initdb pg_ctl postgres` all miss after installing postgresql-16,
# while gosu, installed to /usr/sbin, is already found). The s6 scripts
# (10-pg-initdb.sh, 20-postgres/run, 30-pg-init.sh) invoke these by bare name,
# relying on inherited PATH (gosu execs straight through, keeping the caller's
# environment) -- so this is the one place that needs fixing for them to work
# on this base; the scripts themselves need no changes.
ENV PATH="/usr/lib/postgresql/16/bin:/opt/casmgr/venv/bin:${PATH}"

# Application venv on the system Python 3.12 (see header) -- no more uv /
# standalone-interpreter fetch. The daemon MUST run via THIS interpreter so
# `sys.executable -m <tool>` in code_analysis/core/code_quality/tool_runtime.py
# resolves flake8/mypy/black/isort/bandit from this venv (see
# main.py::_log_quality_tools_selfcheck).
RUN python3 -m venv /opt/casmgr/venv

WORKDIR /opt/casmgr
COPY pyproject.toml ./
COPY code_analysis ./code_analysis
COPY casmgr_entry ./casmgr_entry
COPY scripts/postgres_setup_from_env_config.py ./scripts/postgres_setup_from_env_config.py
COPY docker/casmgr-postgres/docker-entrypoint-initdb.d/01-pgvector.sh ./postgres-init/01-pgvector.sh

# Some source files carry restrictive host-dev-machine permissions (owner-only
# read, no "other" bit); COPY preserves those bits verbatim under root:root, so
# without this the daemon (running as casuser, an arbitrary non-root uid with
# no special group membership -- see 40-casmgr/run) fails at import time with
# PermissionError. World-readable is safe: this is application source, not
# secrets (those live under /var/casmgr/secrets, never copied into the image).
# The venv itself (/opt/casmgr/venv) needs the same a+rX treatment for the same
# reason: casuser gosu's straight into /opt/casmgr/venv/bin/python (see
# 40-casmgr/run). Applied AFTER the editable install so files pip writes
# (egg-info, __pycache__, etc.) are covered too. The compileall pass pre-warms
# the .pyc bytecode cache for the venv's site-packages and the app code at
# BUILD time: PYTHONDONTWRITEBYTECODE=1 (set below) stops the daemon's several
# multiprocessing worker spawns from WRITING new .pyc at runtime, but they
# still READ valid pre-existing ones, skipping from-source recompilation on
# every spawn -- this matters because recompilation was observed to
# occasionally blow past a fixed queue-manager startup timeout under host CPU
# contention.
RUN chmod -R a+rX /opt/casmgr/code_analysis /opt/casmgr/casmgr_entry /opt/casmgr/scripts \
    && /opt/casmgr/venv/bin/pip install --no-cache-dir -e ".[postgres-backup]" \
    && chmod +x ./postgres-init/01-pgvector.sh \
    && /opt/casmgr/venv/bin/python -m compileall -q /opt/casmgr/venv/lib /opt/casmgr/code_analysis /opt/casmgr/casmgr_entry \
    && chmod -R a+rX /opt/casmgr/venv

# s6-overlay service tree (see docker/casmgr/s6/s6-rc.d/*/{up,run} for details).
# Oneshot `up` files are pure execline one-liners (s6-rc-oneshot-run feeds their
# content straight to execlineb, ignoring any shebang) that just exec the real
# bash worker script below; those worker scripts carry the s6-overlay-v3
# `/command/with-contenv` shebang (v2's `/usr/bin/with-contenv` does not exist).
COPY docker/casmgr/s6/s6-rc.d /etc/s6-overlay/s6-rc.d
COPY docker/casmgr/s6/scripts /etc/s6-overlay/scripts
RUN chmod -R +x /etc/s6-overlay/s6-rc.d /etc/s6-overlay/scripts \
    && touch /etc/s6-overlay/s6-rc.d/user/contents.d/40-casmgr \
    && test -x /command/with-contenv \
    && test -x /command/execlineb

# CASMGR_UID/CASMGR_GID: host casuser's real numeric uid/gid, injected at
# container-run time (compose `environment`, sourced from /etc/casmgr/.env on
# the host); service 40-casmgr drops to these via gosu. These ENV values are
# fallback defaults for local/standalone runs only. The existing root-refusal
# guard in code_analysis/core/project_git/execution_context.py (keyed on
# CASMGR_ALLOW_ROOT) is untouched by this change and simply passes, since the
# daemon's euid is now casuser's, not 0.
ENV CASMGR_UID=1000 \
    CASMGR_GID=1000 \
    CASMGR_CONFIG=/etc/casmgr/config.json \
    CASMGR_SECRETS=/var/casmgr/secrets \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 15010

ENTRYPOINT ["/init"]
