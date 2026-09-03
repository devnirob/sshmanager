from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any
from uuid import uuid4


def _unsafe_ssh_value(value: str) -> bool:
    """Return true for values that could be interpreted as SSH options or fields."""
    return not value or value.startswith("-") or any(character.isspace() or ord(character) < 32 for character in value)


@dataclass
class ConnectionProfile:
    id: str
    name: str = "New server"
    host: str = ""
    port: int = 22
    username: str = ""
    remote_path: str = "/"
    key_path: str = ""
    jump_host: str = ""
    notes: str = ""
    save_password: bool = True
    use_agent: bool = True

    @classmethod
    def create(cls, name: str = "New server") -> "ConnectionProfile":
        return cls(id=str(uuid4()), name=name)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConnectionProfile":
        # description was the notes field in the 0.1 profile format.
        migrated = dict(data)
        if "description" in migrated and "notes" not in migrated:
            migrated["notes"] = migrated["description"]
        allowed = {field.name for field in fields(cls)}
        values = {key: value for key, value in migrated.items() if key in allowed}
        values.setdefault("id", str(uuid4()))
        profile = cls(**values)
        if not isinstance(profile.id, str) or not profile.id:
            profile.id = str(uuid4())
        try:
            profile.port = int(profile.port)
        except (TypeError, ValueError):
            profile.port = 22
        for name in ("name", "host", "username", "remote_path", "key_path", "jump_host", "notes"):
            value = getattr(profile, name)
            setattr(profile, name, value if isinstance(value, str) else "")
        profile.save_password = profile.save_password if isinstance(profile.save_password, bool) else True
        profile.use_agent = profile.use_agent if isinstance(profile.use_agent, bool) else True
        profile.remote_path = profile.remote_path or "/"
        return profile

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def target(self) -> str:
        return f"{self.username}@{self.host}" if self.username else self.host

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.name.strip():
            errors.append("Connection name is required.")
        if not self.host.strip():
            errors.append("Host or IP address is required.")
        elif _unsafe_ssh_value(self.host.strip()):
            errors.append("Host cannot begin with '-' or contain whitespace/control characters.")
        if not self.username.strip():
            errors.append("Username is required.")
        elif _unsafe_ssh_value(self.username.strip()):
            errors.append("Username cannot begin with '-' or contain whitespace/control characters.")
        if self.jump_host and _unsafe_ssh_value(self.jump_host.strip()):
            errors.append("Jump host cannot begin with '-' or contain whitespace/control characters.")
        if "\x00" in self.remote_path or "\x00" in self.key_path:
            errors.append("Paths cannot contain NUL characters.")
        if not 1 <= self.port <= 65535:
            errors.append("Port must be between 1 and 65535.")
        return errors
