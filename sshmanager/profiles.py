from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .config import PROFILES_FILE, ensure_app_dirs
from .models import ConnectionProfile


class ProfileStoreError(RuntimeError):
    pass


class ProfileStore:
    def __init__(self, file_path: Path = PROFILES_FILE) -> None:
        self.file_path = file_path

    def load(self) -> list[ConnectionProfile]:
        self._prepare_directory()
        if not self.file_path.exists():
            return []
        try:
            raw = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            raise ProfileStoreError(f"Could not read {self.file_path}: {error}") from error
        if not isinstance(raw, list):
            raise ProfileStoreError("The profile file must contain a JSON list.")
        return [ConnectionProfile.from_dict(item) for item in raw if isinstance(item, dict)]

    def save(self, profiles: list[ConnectionProfile]) -> None:
        self._prepare_directory()
        payload = json.dumps([profile.to_dict() for profile in profiles], indent=2) + "\n"
        temporary_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.file_path.parent,
                prefix="profiles-",
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
            raise ProfileStoreError(f"Could not save profiles: {error}") from error

    def _prepare_directory(self) -> None:
        if self.file_path == PROFILES_FILE:
            ensure_app_dirs()
        else:
            self.file_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.file_path.exists():
            self.file_path.chmod(0o600)
