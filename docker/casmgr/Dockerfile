# casmgr — all-in-one image: PostgreSQL 16 + pgvector, the code_analysis MCP
# daemon, and all its in-process workers, supervised by s6-overlay v3.
#
# Build (from repo root):
#   docker build -f docker/casmgr/Dockerfile -t vasilyvz/casmgr:VERSION .
#
# Runtime bind mounts (rw, casuser-root on the host):
#   /etc/casmgr       config.json, mtls/, docker-compose.yml
#   /var/casmgr       secrets/.env, postgres/{data,cache}, data/, faiss/, locks/,
#                     backups/, trash/, versions/, watch_catalog/, watched/<uuid4>
#   /var/log/casmgr   daemon logs + postgres/
#
# The container runs as root (uid 0) -- code_analysis.main and its workers need
# full access to the casuser-root bind-mounted tree. PostgreSQL still drops
# privileges to uid/gid 999 (this base image's built-in "postgres" user) via
# gosu. Do NOT create a "casmgr" system user/group here: uid/gid 999 already
# belongs to postgres and reusing it would collide.
#
# s6-overlay v3 service tree: docker/casmgr/s6/s6-rc.d/ (see comments in each
# service's up/run script). Boot order: 00-init-dirs -> 10-pg-initdb ->
# 20-postgres (readiness via notification-fd + pg_isready) -> 30-pg-init ->
# 40-casmgr.
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

ARG PGVECTOR_BASE=pgvector/pgvector:pg16
FROM ${PGVECTOR_BASE}

ARG VERSION=dev
LABEL org.opencontainers.image.title="casmgr" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.description="All-in-one Code Analysis Server (casmgr): PostgreSQL 16 + pgvector + code_analysis daemon, s6-overlay supervised"

ARG S6_OVERLAY_VERSION=3.2.3.0

# python3 + venv/pip for the isolated app venv; git for project_git commands;
# ca-certificates for TLS/pip; xz-utils to unpack the s6-overlay tarballs.
# psql/pg_dump/pg_restore/pg_ctl/gosu already ship in the pgvector/pgvector base.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        python3-pip \
        git \
        ca-certificates \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

# s6-overlay v3 (PID 1 supervisor with dependency-ordered service startup).
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz /tmp/s6-overlay-noarch.tar.xz
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-x86_64.tar.xz /tmp/s6-overlay-x86_64.tar.xz
RUN tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz \
    && tar -C / -Jxpf /tmp/s6-overlay-x86_64.tar.xz \
    && rm -f /tmp/s6-overlay-noarch.tar.xz /tmp/s6-overlay-x86_64.tar.xz

# Isolated application venv (avoids PEP 668 / system-Python conflicts). The
# daemon MUST run via THIS interpreter so `sys.executable -m <tool>` in
# code_analysis/core/code_quality/tool_runtime.py resolves flake8/mypy/black/
# isort/bandit from this venv (see main.py::_log_quality_tools_selfcheck).
ENV PATH="/opt/casmgr/venv/bin:${PATH}"
RUN python3 -m venv /opt/casmgr/venv \
    && /opt/casmgr/venv/bin/pip install --no-cache-dir --upgrade pip

WORKDIR /opt/casmgr
COPY pyproject.toml ./
COPY code_analysis ./code_analysis
COPY casmgr_entry ./casmgr_entry
COPY scripts/postgres_setup_from_env_config.py ./scripts/postgres_setup_from_env_config.py
COPY docker/casmgr-postgres/docker-entrypoint-initdb.d/01-pgvector.sh ./postgres-init/01-pgvector.sh

RUN /opt/casmgr/venv/bin/pip install --no-cache-dir -e ".[postgres-backup]" \
    && chmod +x ./postgres-init/01-pgvector.sh

# s6-overlay service tree (see docker/casmgr/s6/s6-rc.d/*/{up,run} for details).
COPY docker/casmgr/s6/s6-rc.d /etc/s6-overlay/s6-rc.d
RUN chmod -R +x /etc/s6-overlay/s6-rc.d \
    && touch /etc/s6-overlay/s6-rc.d/user/contents.d/40-casmgr

# CASMGR_ALLOW_ROOT: a separate phase adds a root-refusal guard in
# code_analysis/core/project_git/execution_context.py keyed on this variable;
# this image runs the daemon as root by design and opts in explicitly.
ENV CASMGR_ALLOW_ROOT=1 \
    CASMGR_CONFIG=/etc/casmgr/config.json \
    CASMGR_SECRETS=/var/casmgr/secrets \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 15010

ENTRYPOINT ["/init"]
