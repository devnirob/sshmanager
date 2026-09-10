from __future__ import annotations

import os
from pathlib import Path

APP_ID = "io.github.nirob.SSHManager"
APP_NAME = "SSH Manager"
VERSION = "2.1.1"


def _xdg_path(variable: str, fallback: Path) -> Path:
    value = os.environ.get(variable)
    return Path(value).expanduser() if value else fallback


CONFIG_DIR = _xdg_path("XDG_CONFIG_HOME", Path.home() / ".config") / "sshmanager"
DATA_DIR = _xdg_path("XDG_DATA_HOME", Path.home() / ".local" / "share") / "sshmanager"
PROFILES_FILE = CONFIG_DIR / "profiles.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
KNOWN_HOSTS_FILE = CONFIG_DIR / "known_hosts"


def ensure_app_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    CONFIG_DIR.chmod(0o700)
    DATA_DIR.chmod(0o700)
    if not KNOWN_HOSTS_FILE.exists():
        KNOWN_HOSTS_FILE.touch(mode=0o600)
    else:
        KNOWN_HOSTS_FILE.chmod(0o600)
