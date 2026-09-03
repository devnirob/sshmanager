#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"
python3 -m unittest discover -s tests -p 'test*.py'
python3 -m compileall -q sshmanager tests
if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate data/sshmanager.desktop
fi
if command -v appstreamcli >/dev/null 2>&1; then
    appstreamcli validate --no-net data/io.github.nirob.SSHManager.metainfo.xml
fi
echo "All tests and compile checks passed."
