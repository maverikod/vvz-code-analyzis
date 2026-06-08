# casmgr-postgres — versioned PostgreSQL + pgvector image for casmgr-server deployments.
#
# Build via scripts/release_build.sh (version tag is shared with the Debian package).
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

ARG PGVECTOR_BASE=pgvector/pgvector:pg16
FROM ${PGVECTOR_BASE}

ARG VERSION=dev
LABEL org.opencontainers.image.title="casmgr-postgres" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.description="PostgreSQL 16 with pgvector for Code Analysis Server (casmgr)"

# Optional first-boot hooks (extensions, locale tweaks). Data dir is always a host mount.
COPY docker/casmgr-postgres/docker-entrypoint-initdb.d/ /docker-entrypoint-initdb.d/
