#!/bin/bash
# Install casmgr-server files into debian staging directory.
set -euo pipefail

CURDIR="${1:?usage: install-package.sh CURDIR}"

ST="${CURDIR}/debian/casmgr-server"

install -d "${ST}/usr/lib/casmgr-server"
cp -a "${CURDIR}/code_analysis" "${CURDIR}/casmgr_entry" \
    "${CURDIR}/pyproject.toml" \
    "${ST}/usr/lib/casmgr-server/"
install -d "${ST}/usr/lib/casmgr-server/scripts/lib"
install -m 644 "${CURDIR}/scripts/lib/casmgr-runtime.sh" \
    "${ST}/usr/lib/casmgr-server/scripts/lib/casmgr-runtime.sh"
install -m 644 "${CURDIR}/scripts/lib/casmgr-entry.sh" \
    "${ST}/usr/lib/casmgr-server/scripts/lib/casmgr-entry.sh"
install -m 755 "${CURDIR}/scripts/casmgr" "${ST}/usr/lib/casmgr-server/scripts/casmgr"
install -m 755 "${CURDIR}/scripts/casmgr-config" "${ST}/usr/lib/casmgr-server/scripts/casmgr-config"
install -m 755 "${CURDIR}/scripts/casmgr-config-generate" \
    "${ST}/usr/lib/casmgr-server/scripts/casmgr-config-generate"
install -m 755 "${CURDIR}/scripts/casmgr-config-validate" \
    "${ST}/usr/lib/casmgr-server/scripts/casmgr-config-validate"
install -m 755 "${CURDIR}/scripts/casmgr_ensure_instance_uuid.py" \
    "${ST}/usr/lib/casmgr-server/scripts/casmgr_ensure_instance_uuid.py"
install -d "${ST}/usr/lib/casmgr-server/docs"
install -m 644 "${CURDIR}/docs/README.md" "${ST}/usr/lib/casmgr-server/docs/README.md"

install -d "${ST}/usr/bin"
install -m 755 "${CURDIR}/scripts/casmgr" "${ST}/usr/bin/casmgr"
install -m 755 "${CURDIR}/scripts/casmgr-config" "${ST}/usr/bin/casmgr-config"
install -m 755 "${CURDIR}/scripts/casmgr-config-generate" "${ST}/usr/bin/casmgr-config-generate"
install -m 755 "${CURDIR}/scripts/casmgr-config-validate" "${ST}/usr/bin/casmgr-config-validate"

install -d "${ST}/lib/systemd/system"
install -m 644 "${CURDIR}/packaging/systemd/casmgr-server.service" \
    "${ST}/lib/systemd/system/"
install -m 644 "${CURDIR}/packaging/systemd/casmgr-postgres.service" \
    "${ST}/lib/systemd/system/"

install -d "${ST}/usr/lib/casmgr/bin"
install -m 755 "${CURDIR}/packaging/bin/casmgr-pg-common.sh" \
    "${ST}/usr/lib/casmgr/bin/"
install -m 755 "${CURDIR}/packaging/bin/casmgr-postgres-container" \
    "${ST}/usr/lib/casmgr/bin/"
install -m 755 "${CURDIR}/packaging/bin/casmgr-pg-init" \
    "${ST}/usr/lib/casmgr/bin/"
install -m 755 "${CURDIR}/packaging/bin/casmgr-pg-set-password" \
    "${ST}/usr/lib/casmgr/bin/"
install -m 755 "${CURDIR}/packaging/bin/casmgr-install-server-config" \
    "${ST}/usr/lib/casmgr/bin/"

install -d "${ST}/usr/share/casmgr-server/scripts"
install -m 644 "${CURDIR}/scripts/postgres_setup_from_env_config.py" \
    "${ST}/usr/share/casmgr-server/scripts/"

install -d "${ST}/usr/share/casmgr"
if [[ -f "${CURDIR}/debian/casmgr-docker-image" ]]; then
    install -m 644 "${CURDIR}/debian/casmgr-docker-image" \
        "${ST}/usr/share/casmgr/docker-image"
else
    echo "vasilyvz/casmgr-postgres:unknown" > "${ST}/usr/share/casmgr/docker-image"
fi

if [[ ! -f "${CURDIR}/packaging/config.json.template" ]]; then
    echo "ERROR: ${CURDIR}/packaging/config.json.template missing" >&2
    exit 1
fi

install -d "${ST}/etc/casmgr/postgres"
install -m 640 "${CURDIR}/packaging/config.json.template" \
    "${ST}/etc/casmgr/config.json"

install -d "${ST}/var/casmgr/secrets"
install -m 640 "${CURDIR}/packaging/secrets.env.template" \
    "${ST}/var/casmgr/secrets/.env"

install -d "${ST}/usr/share/casmgr-server"
install -m 644 "${CURDIR}/packaging/config.json.template" \
    "${ST}/usr/share/casmgr-server/config.json.template"
install -m 644 "${CURDIR}/packaging/secrets.env.template" \
    "${ST}/usr/share/casmgr-server/secrets.env.template"

install -d "${ST}/usr/share/doc/casmgr-server"
install -m 644 "${CURDIR}/packaging/config.json.template" \
    "${ST}/usr/share/doc/casmgr-server/config.json.template"
install -m 644 "${CURDIR}/packaging/secrets.env.template" \
    "${ST}/usr/share/doc/casmgr-server/secrets.env.template"
install -m 644 "${CURDIR}/docs/CASMGR_DEPLOYMENT.md" \
    "${ST}/usr/share/doc/casmgr-server/"

install -d "${ST}/usr/share/man/man8"
install -m 644 "${CURDIR}/packaging/man/casmgr-server.8" \
    "${ST}/usr/share/man/man8/"
install -d "${ST}/usr/share/man/man1"
install -m 644 "${CURDIR}/packaging/man/casmgr-config.1" \
    "${ST}/usr/share/man/man1/"

install -d "${ST}/usr/share/info"
if command -v makeinfo >/dev/null 2>&1; then
    makeinfo --no-split -o "${ST}/usr/share/info/casmgr-server.info" \
        "${CURDIR}/packaging/info/casmgr-server.texi"
elif [[ -f "${CURDIR}/packaging/info/casmgr-server.info" ]]; then
    install -m 644 "${CURDIR}/packaging/info/casmgr-server.info" \
        "${ST}/usr/share/info/"
fi

install -d "${ST}/usr/sbin"
ln -sf ../lib/casmgr/bin/casmgr-postgres-container \
    "${ST}/usr/sbin/casmgr-postgres-container"
ln -sf ../lib/casmgr/bin/casmgr-pg-init \
    "${ST}/usr/sbin/casmgr-pg-init"
ln -sf ../lib/casmgr/bin/casmgr-pg-set-password \
    "${ST}/usr/sbin/casmgr-pg-set-password"
