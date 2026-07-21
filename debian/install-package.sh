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
install -m 755 "${CURDIR}/packaging/bin/casmgr-compose-ulimit-patch" \
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
# /etc/casmgr/config.json MUST be strict JSON (no comments): besides the app's
# own commentjson-tolerant loader, mcp_proxy_adapter does an eager import-time
# json.load('./config.json') that rejects the "#"/"//" documentation comments the
# source template carries. With 40-casmgr/run's `cd /etc/casmgr` that resolves to
# this file and crash-loops the daemon on a JSONC config. Emit strict JSON from
# the (documented, JSONC) source template at stage time; reuse it for the runtime
# template that postinst copies from when config.json is absent.
_casmgr_py="python3"
[[ -x "${CURDIR}/.venv/bin/python" ]] && _casmgr_py="${CURDIR}/.venv/bin/python"
"${_casmgr_py}" -c "import commentjson" 2>/dev/null || {
    echo "ERROR: commentjson required to emit strict-JSON /etc/casmgr/config.json (pip install commentjson)" >&2
    exit 1
}
_casmgr_cfg_strict="$(mktemp)"
"${_casmgr_py}" -c "import commentjson, json, sys; json.dump(commentjson.load(open(sys.argv[1])), open(sys.argv[2], 'w'), indent=2, ensure_ascii=False)" \
    "${CURDIR}/packaging/config.json.template" "${_casmgr_cfg_strict}"
python3 -c "import json,sys; json.load(open(sys.argv[1]))" "${_casmgr_cfg_strict}" \
    || { echo "ERROR: emitted /etc/casmgr/config.json is not strict JSON" >&2; exit 1; }
install -m 640 "${_casmgr_cfg_strict}" \
    "${ST}/etc/casmgr/config.json"
install -m 644 "${CURDIR}/docker/docker-compose.allinone.yml" \
    "${ST}/etc/casmgr/docker-compose.yml"
printf 'CASMGR_VERSION=%s\n' "$VERSION" > "${ST}/etc/casmgr/.env"
chmod 644 "${ST}/etc/casmgr/.env"

install -d "${ST}/var/casmgr/secrets"
install -m 640 "${CURDIR}/packaging/secrets.env.template" \
    "${ST}/var/casmgr/secrets/.env"

install -d "${ST}/usr/share/casmgr-server"
# Strict-JSON runtime template (postinst's casmgr-install-server-config copies
# this verbatim to /etc/casmgr/config.json when absent — must also be strict).
install -m 644 "${_casmgr_cfg_strict}" \
    "${ST}/usr/share/casmgr-server/config.json.template"
rm -f "${_casmgr_cfg_strict}"
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
