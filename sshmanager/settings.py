from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import SETTINGS_FILE, ensure_app_dirs


DEFAULT_THEME = "vscode-dark"
THEME_CHOICES = (
    ("vscode-dark", "VS Code Dark"),
    ("light", "Light"),
    ("system", "System"),
)
VALID_THEMES = {value for value, _label in THEME_CHOICES}


class SettingsStoreError(RuntimeError):
    pass


@dataclass
class AppSettings:
    theme: str = DEFAULT_THEME

    @classmethod
    def from_dict(cls, data: object) -> "AppSettings":
        if not isinstance(data, dict):
            return cls()
        theme = data.get("theme", DEFAULT_THEME)
        return cls(theme=theme if theme in VALID_THEMES else DEFAULT_THEME)

    def to_dict(self) -> dict[str, str]:
        return {"theme": self.theme}


class SettingsStore:
    def __init__(self, file_path: Path = SETTINGS_FILE) -> None:
        self.file_path = file_path

    def load(self) -> AppSettings:
        self._prepare_directory()
        if not self.file_path.exists():
            return AppSettings()
        try:
            raw = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return AppSettings()
        return AppSettings.from_dict(raw)

    def save(self, settings: AppSettings) -> None:
        self._prepare_directory()
        payload = json.dumps(settings.to_dict(), indent=2) + "\n"
        temporary_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.file_path.parent,
                prefix="settings-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_name = handle.name
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, self.file_path)
        except OSError as error:
            if temporary_name:
                Path(temporary_name).unlink(missing_ok=True)
            raise SettingsStoreError(f"Could not save settings: {error}") from error

    def _prepare_directory(self) -> None:
        if self.file_path == SETTINGS_FILE:
            ensure_app_dirs()
        else:
            self.file_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.file_path.exists():
            self.file_path.chmod(0o600)
