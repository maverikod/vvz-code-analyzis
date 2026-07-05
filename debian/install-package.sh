#!/bin/bash
# Install casmgr-server files into debian staging directory.
set -euo pipefail

CURDIR="${1:?usage: install-package.sh CURDIR}"

ST="${CURDIR}/debian/casmgr-server"

VERSION="$(grep -m1 '^version' "${CURDIR}/pyproject.toml" | sed -E 's/^version[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/')"
if [[ -z "$VERSION" ]]; then
    echo "ERROR: could not determine version from ${CURDIR}/pyproject.toml" >&2
    exit 1
fi

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
install -d "${ST}/usr/lib/casmgr-server/docs"
install -m 644 "${CURDIR}/docs/README.md" "${ST}/usr/lib/casmgr-server/docs/README.md"

install -d "${ST}/usr/bin"
install -m 755 "${CURDIR}/scripts/casmgr" "${ST}/usr/bin/casmgr"
install -m 755 "${CURDIR}/scripts/casmgr-config" "${ST}/usr/bin/casmgr-config"
install -m 755 "${CURDIR}/scripts/casmgr-config-generate" "${ST}/usr/bin/casmgr-config-generate"
install -m 755 "${CURDIR}/scripts/casmgr-config-validate" "${ST}/usr/bin/casmgr-config-validate"

install -d "${ST}/lib/systemd/system"
install -m 644 "${CURDIR}/packaging/systemd/casmgr.service" \
    "${ST}/lib/systemd/system/"

install -d "${ST}/usr/lib/casmgr/bin"
install -m 755 "${CURDIR}/packaging/bin/casmgr-pg-set-password" \
    "${ST}/usr/lib/casmgr/bin/"
install -m 755 "${CURDIR}/packaging/bin/casmgr-install-server-config" \
    "${ST}/usr/lib/casmgr/bin/"

install -d "${ST}/usr/share/casmgr"
if [[ -f "${CURDIR}/debian/casmgr-docker-image" ]]; then
    install -m 644 "${CURDIR}/debian/casmgr-docker-image" \
        "${ST}/usr/share/casmgr/docker-image"
else
    echo "vasilyvz/casmgr:${VERSION}" > "${ST}/usr/share/casmgr/docker-image"
fi
if [[ -f "${CURDIR}/debian/casmgr-image.tar.gz" ]]; then
    install -m 644 "${CURDIR}/debian/casmgr-image.tar.gz" \
        "${ST}/usr/share/casmgr/casmgr-image.tar.gz"
fi

if [[ ! -f "${CURDIR}/packaging/config.json.template" ]]; then
    echo "ERROR: ${CURDIR}/packaging/config.json.template missing" >&2
    exit 1
fi

install -d "${ST}/etc/casmgr"
install -m 640 "${CURDIR}/packaging/config.json.template" \
    "${ST}/etc/casmgr/config.json"
install -m 644 "${CURDIR}/docker/docker-compose.allinone.yml" \
    "${ST}/etc/casmgr/docker-compose.yml"
printf 'CASMGR_VERSION=%s\n' "$VERSION" > "${ST}/etc/casmgr/.env"
chmod 644 "${ST}/etc/casmgr/.env"

install -d "${ST}/var/casmgr/secrets"
install -m 640 "${CURDIR}/packaging/secrets.env.template" \
    "${ST}/var/casmgr/secrets/.env"

install -d "${ST}/usr/share/casmgr-server"
install -m 644 "${CURDIR}/packaging/config.json.template" \
    "${ST}/usr/share/casmgr-server/config.json.template"
install -m 644 "${CURDIR}/packaging/secrets.env.template" \
    "${ST}/usr/share/casmgr-server/secrets.env.template"
install -d "${ST}/usr/share/casmgr-server/watch-catalog-example"
cp -a "${CURDIR}/packaging/watch-catalog-example/." \
    "${ST}/usr/share/casmgr-server/watch-catalog-example/"

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
ln -sf ../lib/casmgr/bin/casmgr-pg-set-password \
    "${ST}/usr/sbin/casmgr-pg-set-password"
