#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${HOME}/.local/share/sshmanager/app"
BIN_DIR="${HOME}/.local/bin"
DESKTOP_DIR="${HOME}/.local/share/applications"
ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"
APP_ID="io.github.nirob.SSHManager"

mkdir -p "${APP_DIR}" "${BIN_DIR}" "${DESKTOP_DIR}" "${ICON_DIR}"
rm -rf "${APP_DIR}/sshmanager" "${APP_DIR}/bin"
cp -r "${ROOT_DIR}/sshmanager" "${APP_DIR}/sshmanager"
cp -r "${ROOT_DIR}/bin" "${APP_DIR}/bin"
find "${APP_DIR}" -type d -name __pycache__ -prune -exec rm -rf {} +

printf '%s\n' '#!/usr/bin/env bash' \
    'exec python3 "${HOME}/.local/share/sshmanager/app/bin/sshmanager" "$@"' \
    > "${BIN_DIR}/sshmanager"
chmod 0755 "${BIN_DIR}/sshmanager"
install -m 0644 "${ROOT_DIR}/data/sshmanager.desktop" "${DESKTOP_DIR}/${APP_ID}.desktop"
install -m 0644 "${ROOT_DIR}/data/sshmanager.svg" "${ICON_DIR}/${APP_ID}.svg"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${DESKTOP_DIR}" >/dev/null 2>&1 || true
fi

echo "SSH Manager installed for ${USER}."
if ! "${BIN_DIR}/sshmanager" --check; then
    echo
    echo "Install the missing packages shown above, then run: sshmanager"
    exit 1
fi
echo "Run 'sshmanager' or open SSH Manager from the application menu."
