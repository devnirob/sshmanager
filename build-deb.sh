#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(PYTHONPATH="${ROOT_DIR}" python3 -c 'from sshmanager.config import VERSION; print(VERSION)')"
ARCH="$(dpkg --print-architecture)"
TRIPLET="$(dpkg-architecture -qDEB_HOST_MULTIARCH)"
PACKAGE_NAME="ssh-manager_${VERSION}_${ARCH}"
OUTPUT="${ROOT_DIR}/dist/${PACKAGE_NAME}.deb"
APP_ID="io.github.nirob.SSHManager"

if [[ "${ARCH}" != "amd64" ]]; then
    echo "This offline builder currently supports amd64; detected ${ARCH}." >&2
    exit 1
fi

for command in dpkg-deb dpkg-architecture ldd file; do
    if ! command -v "${command}" >/dev/null 2>&1; then
        echo "Missing build command: ${command}" >&2
        exit 1
    fi
done

BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/sshmanager-deb.XXXXXX")"
cleanup() {
    if [[ "${KEEP_BUILD:-0}" == "1" ]]; then
        echo "Kept staging tree for inspection: ${BUILD_DIR}"
    else
        rm -rf -- "${BUILD_DIR}"
    fi
}
trap cleanup EXIT
PACKAGE_ROOT="${BUILD_DIR}/package"
APP_ROOT="${PACKAGE_ROOT}/opt/sshmanager"
RUNTIME_ROOT="${APP_ROOT}/runtime"

mkdir -p \
    "${PACKAGE_ROOT}/DEBIAN" \
    "${APP_ROOT}/app" \
    "${RUNTIME_ROOT}/usr/bin" \
    "${RUNTIME_ROOT}/usr/lib/${TRIPLET}" \
    "${RUNTIME_ROOT}/usr/lib/python3/dist-packages" \
    "${PACKAGE_ROOT}/usr/bin" \
    "${PACKAGE_ROOT}/usr/share/applications" \
    "${PACKAGE_ROOT}/usr/share/doc/ssh-manager" \
    "${PACKAGE_ROOT}/usr/share/icons/hicolor/scalable/apps" \
    "${PACKAGE_ROOT}/usr/share/metainfo" \
    "${ROOT_DIR}/dist"

cp -a "${ROOT_DIR}/sshmanager" "${APP_ROOT}/app/sshmanager"
find "${APP_ROOT}/app" -type d -name __pycache__ -prune -exec rm -rf -- {} +

copy_runtime_path() {
    local source="$1"
    if [[ ! -e "${source}" && ! -L "${source}" ]]; then
        return
    fi
    cp -a --parents "${source}" "${RUNTIME_ROOT}"
    if [[ -L "${source}" ]]; then
        local resolved
        resolved="$(readlink -f "${source}")"
        cp -a --parents "${resolved}" "${RUNTIME_ROOT}"
    fi
}

# Private Python runtime and the Python packages used by the application.
PYTHON_BINARY="$(readlink -f "$(command -v python3)")"
copy_runtime_path "${PYTHON_BINARY}"
ln -s "$(basename "${PYTHON_BINARY}")" "${RUNTIME_ROOT}/usr/bin/python3"
cp -a /usr/lib/python3.* "${RUNTIME_ROOT}/usr/lib/"

shopt -s nullglob
PYTHON_MODULE_PATTERNS=(
    gi 'gi-*.egg-info' 'PyGObject-*.dist-info'
    cairo 'pycairo-*.egg-info' 'pycairo-*.dist-info'
    paramiko 'paramiko-*.egg-info' 'paramiko-*.dist-info'
    cryptography 'cryptography-*.egg-info' 'cryptography-*.dist-info'
    bcrypt 'bcrypt-*.egg-info' 'bcrypt-*.dist-info'
    nacl 'PyNaCl-*.egg-info' 'PyNaCl-*.dist-info'
    invoke 'invoke-*.egg-info' 'invoke-*.dist-info'
    '_cffi_backend*.so'
)
for pattern in "${PYTHON_MODULE_PATTERNS[@]}"; do
    for source in /usr/lib/python3/dist-packages/${pattern}; do
        cp -a "${source}" "${RUNTIME_ROOT}/usr/lib/python3/dist-packages/"
    done
done
shopt -u nullglob

# GI metadata, GTK/VTE/Secret data, icon themes, and dynamically loaded modules.
cp -a "/usr/lib/${TRIPLET}/girepository-1.0" "${RUNTIME_ROOT}/usr/lib/${TRIPLET}/"
for source in \
    "/usr/lib/${TRIPLET}/gtk-3.0" \
    "/usr/lib/${TRIPLET}/gdk-pixbuf-2.0" \
    "/usr/lib/${TRIPLET}/gio/modules" \
    /usr/share/glib-2.0/schemas \
    /usr/share/themes/Adwaita \
    /usr/share/icons/Adwaita \
    /usr/share/icons/hicolor \
    /usr/share/mime; do
    if [[ -e "${source}" ]]; then
        cp -a --parents "${source}" "${RUNTIME_ROOT}"
    fi
done

# SSH executables are bundled so password, key, agent, and jump-host sessions do
# not require openssh-client or sshpass to be downloaded during installation.
copy_runtime_path /usr/bin/ssh
copy_runtime_path /usr/bin/sshpass
if [[ -d /usr/lib/openssh ]]; then
    cp -a --parents /usr/lib/openssh "${RUNTIME_ROOT}"
fi

NATIVE_SEEDS=(
    "/usr/lib/${TRIPLET}/libgtk-3.so.0"
    "/usr/lib/${TRIPLET}/libvte-2.91.so.0"
    "/usr/lib/${TRIPLET}/libsecret-1.so.0"
    "${PYTHON_BINARY}"
    /usr/bin/ssh
    /usr/bin/sshpass
)

# Copy every non-glibc shared-library dependency of the runtime and its plugins.
# glibc remains the only base-system dependency and is present on Debian/Ubuntu.
declare -A SEEN_ELF=()
ELF_QUEUE=()
for seed in "${NATIVE_SEEDS[@]}"; do
    [[ -e "${seed}" ]] && ELF_QUEUE+=("${seed}")
done
while IFS= read -r candidate; do
    ELF_QUEUE+=("${candidate}")
done < <(find \
    /usr/lib/python3/dist-packages/gi \
    /usr/lib/python3/dist-packages/cairo \
    /usr/lib/python3/dist-packages/cryptography \
    /usr/lib/python3/dist-packages/bcrypt \
    /usr/lib/python3/dist-packages/nacl \
    "/usr/lib/${TRIPLET}/gtk-3.0" \
    "/usr/lib/${TRIPLET}/gdk-pixbuf-2.0" \
    "/usr/lib/${TRIPLET}/gio/modules" \
    -type f -exec file {} + 2>/dev/null | awk -F: '/ELF/{print $1}')

queue_index=0
while (( queue_index < ${#ELF_QUEUE[@]} )); do
    elf="${ELF_QUEUE[queue_index]}"
    ((queue_index += 1))
    elf="$(readlink -f "${elf}")"
    [[ -n "${SEEN_ELF[${elf}]:-}" ]] && continue
    SEEN_ELF["${elf}"]=1
    copy_runtime_path "${elf}"
    while IFS= read -r library; do
        case "$(basename "${library}")" in
            libc.so.*|libm.so.*|libpthread.so.*|libdl.so.*|librt.so.*|libresolv.so.*|libutil.so.*|ld-linux-*.so.*)
                continue
                ;;
        esac
        copy_runtime_path "${library}"
        ELF_QUEUE+=("${library}")
    done < <(ldd "${elf}" 2>/dev/null | awk '/=> \//{print $3} /^\//{print $1}' | sort -u)
done

# Make module caches relocatable to the fixed private installation prefix.
while IFS= read -r cache; do
    sed -i "s#${RUNTIME_ROOT}#/opt/sshmanager/runtime#g; s#\"/usr/#\"/opt/sshmanager/runtime/usr/#g" "${cache}"
done < <(find "${RUNTIME_ROOT}" -type f \( -name loaders.cache -o -name immodules.cache \))

find "${RUNTIME_ROOT}" -type d -name __pycache__ -prune -exec rm -rf -- {} +

cat > "${PACKAGE_ROOT}/usr/bin/sshmanager" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="${SSHMANAGER_ROOT:-/opt/sshmanager}"
RUNTIME="${APP_ROOT}/runtime"
TRIPLET="x86_64-linux-gnu"
export PYTHONHOME="${RUNTIME}/usr"
export PYTHONPATH="${APP_ROOT}/app:${RUNTIME}/usr/lib/python3/dist-packages"
export LD_LIBRARY_PATH="${RUNTIME}/lib/${TRIPLET}:${RUNTIME}/usr/lib/${TRIPLET}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export GI_TYPELIB_PATH="${RUNTIME}/usr/lib/${TRIPLET}/girepository-1.0"
export GSETTINGS_SCHEMA_DIR="${RUNTIME}/usr/share/glib-2.0/schemas"
export GIO_EXTRA_MODULES="${RUNTIME}/usr/lib/${TRIPLET}/gio/modules"
export GTK_PATH="${RUNTIME}/usr/lib/${TRIPLET}/gtk-3.0"
export GDK_PIXBUF_MODULE_FILE="${RUNTIME}/usr/lib/${TRIPLET}/gdk-pixbuf-2.0/2.10.0/loaders.cache"
export XDG_DATA_DIRS="${RUNTIME}/usr/share${XDG_DATA_DIRS:+:${XDG_DATA_DIRS}}"
export PATH="${RUNTIME}/usr/bin:${PATH}"
exec "${RUNTIME}/usr/bin/python3" -m sshmanager "$@"
LAUNCHER
chmod 0755 "${PACKAGE_ROOT}/usr/bin/sshmanager"

install -m 0644 "${ROOT_DIR}/data/sshmanager.desktop" "${PACKAGE_ROOT}/usr/share/applications/${APP_ID}.desktop"
install -m 0644 "${ROOT_DIR}/data/sshmanager.svg" "${PACKAGE_ROOT}/usr/share/icons/hicolor/scalable/apps/${APP_ID}.svg"
install -m 0644 "${ROOT_DIR}/data/${APP_ID}.metainfo.xml" "${PACKAGE_ROOT}/usr/share/metainfo/${APP_ID}.metainfo.xml"
install -m 0644 "${ROOT_DIR}/README.md" "${PACKAGE_ROOT}/usr/share/doc/ssh-manager/README.md"
install -m 0644 "${ROOT_DIR}/SECURITY.md" "${PACKAGE_ROOT}/usr/share/doc/ssh-manager/SECURITY.md"
install -m 0644 "${ROOT_DIR}/SECURITY_AUDIT.md" "${PACKAGE_ROOT}/usr/share/doc/ssh-manager/SECURITY_AUDIT.md"
install -m 0644 "${ROOT_DIR}/CHANGELOG.md" "${PACKAGE_ROOT}/usr/share/doc/ssh-manager/CHANGELOG.md"

# Retain copyright notices for every discoverable package represented in the
# private runtime, plus data-only packages that do not own an ELF seed.
BUNDLED_PACKAGES=(
    python3.13-minimal python3.13 python3-gi python3-cairo python3-paramiko \
    python3-bcrypt python3-cryptography python3-nacl libgtk-3-0t64 \
    libgtk-3-common libvte-2.91-0 libvte-2.91-common libsecret-1-0 \
    adwaita-icon-theme hicolor-icon-theme shared-mime-info openssh-client sshpass
)
for elf in "${!SEEN_ELF[@]}"; do
    while IFS= read -r owner; do
        [[ -n "${owner}" ]] && BUNDLED_PACKAGES+=("${owner%%:*}")
    done < <(dpkg-query -S "${elf}" 2>/dev/null | sed 's/: .*//' || true)
done
mapfile -t BUNDLED_PACKAGES < <(printf '%s\n' "${BUNDLED_PACKAGES[@]}" | sort -u)
for package in "${BUNDLED_PACKAGES[@]}"; do
    copyright="/usr/share/doc/${package}/copyright"
    if [[ -f "${copyright}" ]]; then
        install -D -m 0644 "${copyright}" "${PACKAGE_ROOT}/usr/share/doc/ssh-manager/third-party/${package}.copyright"
    fi
done

find "${PACKAGE_ROOT}" -type d -exec chmod 0755 {} +
find "${APP_ROOT}/app" -type f -exec chmod 0644 {} +
find "${RUNTIME_ROOT}" -type f -perm /022 -exec chmod go-w {} +

INSTALLED_SIZE="$(du -sk "${PACKAGE_ROOT}" | awk '{print $1}')"
cat > "${PACKAGE_ROOT}/DEBIAN/control" <<CONTROL
Package: ssh-manager
Version: ${VERSION}
Section: net
Priority: optional
Architecture: ${ARCH}
Depends: libc6 (>= 2.39)
Installed-Size: ${INSTALLED_SIZE}
Maintainer: Devnirob <robni6970@gmail.com>
Homepage: https://github.com/devnirob/sshmanager
Description: Tabbed SSH terminal and SFTP client for Linux
 A MobaXterm and FileZilla alternative for Linux with saved server profiles,
 independent SSH/SFTP tabs, secure host-key verification, and dual-pane file
 management. Includes a private offline runtime; no dependency download is
 needed on a compatible amd64 Debian or Ubuntu desktop.
CONTROL

cat > "${PACKAGE_ROOT}/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
exit 0
POSTINST
chmod 0755 "${PACKAGE_ROOT}/DEBIAN/postinst"
cp "${PACKAGE_ROOT}/DEBIAN/postinst" "${PACKAGE_ROOT}/DEBIAN/postrm"

# This check uses only the private runtime staged into the package.
PYTHONDONTWRITEBYTECODE=1 SSHMANAGER_ROOT="${APP_ROOT}" "${PACKAGE_ROOT}/usr/bin/sshmanager" --check

dpkg-deb --root-owner-group --build "${PACKAGE_ROOT}" "${OUTPUT}"
(
    cd "${ROOT_DIR}/dist"
    sha256sum "$(basename "${OUTPUT}")" > "$(basename "${OUTPUT}").sha256"
    chmod 0644 "$(basename "${OUTPUT}").sha256"
)
echo "Built offline package: dist/$(basename "${OUTPUT}")"
du -h "${OUTPUT}"
echo "Install without network access: sudo apt install ./dist/$(basename "${OUTPUT}")"
