from __future__ import annotations

import gi

gi.require_version("Secret", "1")
from gi.repository import Secret

from .config import APP_NAME

SCHEMA = Secret.Schema.new(
    "io.github.nirob.SSHManager",
    Secret.SchemaFlags.NONE,
    {"profile-id": Secret.SchemaAttributeType.STRING},
)


class PasswordStoreError(RuntimeError):
    pass


class PasswordStore:
    def save(self, profile_id: str, password: str) -> None:
        if not password:
            self.clear(profile_id)
            return
        try:
            Secret.password_store_sync(
                SCHEMA,
                {"profile-id": profile_id},
                Secret.COLLECTION_DEFAULT,
                f"{APP_NAME} saved login",
                password,
                None,
            )
        except Exception as error:
            raise PasswordStoreError(f"The Linux keyring could not save the password: {error}") from error

    def load(self, profile_id: str) -> str:
        try:
            return Secret.password_lookup_sync(SCHEMA, {"profile-id": profile_id}, None) or ""
        except Exception as error:
            raise PasswordStoreError(f"The Linux keyring could not read the password: {error}") from error

    def clear(self, profile_id: str) -> None:
        try:
            Secret.password_clear_sync(SCHEMA, {"profile-id": profile_id}, None)
        except Exception as error:
            raise PasswordStoreError(f"The Linux keyring could not remove the password: {error}") from error
