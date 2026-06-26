# casmgr-server — Code Analysis MCP server (application + workers in one image).
#
# Build:
#   docker build -f docker/casmgr-server/Dockerfile -t vasilyvz/casmgr-server:TAG .
#
# Runtime mounts (see docs/CASMGR_DOCKER.md):
#   /etc/casmgr/config.json
#   /var/casmgr/secrets, /var/casmgr/data, /var/log/casmgr
#   /watched/<name> — one bind mount per watch root (direct children of /watched)
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

ARG PYTHON_IMAGE=python:3.12-slim-bookworm
FROM ${PYTHON_IMAGE}

ARG VERSION=dev
LABEL org.opencontainers.image.title="casmgr-server" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.description="Code Analysis MCP server (casmgr-server)"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 999 casmgr \
    && useradd --system --uid 999 --gid casmgr --home-dir /opt/casmgr-server --shell /usr/sbin/nologin casmgr

WORKDIR /opt/casmgr-server

COPY pyproject.toml ./
COPY code_analysis ./code_analysis
COPY casmgr_entry ./casmgr_entry
RUN mkdir -p /usr/share/info
COPY packaging/info/casmgr-server.info /usr/share/info/casmgr-server.info

RUN pip install --no-cache-dir -e ".[postgres-backup]"

COPY docker/casmgr-server/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /watched /etc/casmgr /var/casmgr /var/log/casmgr \
    && chown -R casmgr:casmgr /opt/casmgr-server /watched /var/casmgr /var/log/casmgr

ENV CASMGR_WATCH_ROOT=/watched \
    CASMGR_CONFIG=/etc/casmgr/config.json \
    CASMGR_SECRETS=/var/casmgr/secrets \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER casmgr

EXPOSE 15010

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["--foreground"]
