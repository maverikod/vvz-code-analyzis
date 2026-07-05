#!/command/with-contenv bash
# Oneshot (root): ensure casuser/casgrp exist with the host-injected
# CASMGR_UID/CASMGR_GID, create casuser's HOME, and chown the daemon-writable
# state directories so the code_analysis daemon (started as casuser in
# 40-casmgr) can write to them. PostgreSQL dirs stay 999:999 (see
# 00-init-dirs); /etc/casmgr (host-provisioned config) is never chowned here.
set -euo pipefail

: "${CASMGR_UID:?CASMGR_UID not set}"
: "${CASMGR_GID:?CASMGR_GID not set}"

# gid: reuse an existing group at this gid if one exists (e.g. a base-image
# system group already sitting on this number); otherwise create casgrp.
if getent group "${CASMGR_GID}" >/dev/null 2>&1; then
    group_name="$(getent group "${CASMGR_GID}" | cut -d: -f1)"
else
    groupadd -g "${CASMGR_GID}" casgrp
    group_name="casgrp"
fi

# uid: same idea -- reuse an existing user at this uid if one is already
# taken (getpwuid() in the app just needs SOME passwd entry to resolve),
# otherwise create casuser with a real HOME.
if getent passwd "${CASMGR_UID}" >/dev/null 2>&1; then
    user_name="$(getent passwd "${CASMGR_UID}" | cut -d: -f1)"
else
    useradd -u "${CASMGR_UID}" -g "${group_name}" -d /var/casmgr/home/casuser -m -s /usr/sbin/nologin casuser
    user_name="casuser"
fi

mkdir -p /var/casmgr/home/casuser
chown "${CASMGR_UID}:${CASMGR_GID}" /var/casmgr/home/casuser

mkdir -p /var/log/casmgr
chown -R "${CASMGR_UID}:${CASMGR_GID}" \
    /var/casmgr/data \
    /var/casmgr/faiss \
    /var/casmgr/locks \
    /var/casmgr/backups \
    /var/casmgr/trash \
    /var/casmgr/versions \
    /var/casmgr/watch_catalog \
    /var/casmgr/watched \
    /var/casmgr/secrets \
    /var/casmgr/home \
    /var/log/casmgr

echo "05-init-user: ${user_name}(${CASMGR_UID}):${group_name}(${CASMGR_GID}) ready; daemon-writable dirs chowned."
