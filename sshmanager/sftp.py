from __future__ import annotations

import importlib
import base64
import hashlib
import os
import posixpath
import shlex
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from .config import KNOWN_HOSTS_FILE, ensure_app_dirs
from .models import ConnectionProfile

ProgressCallback = Callable[[int, int], None]


class SFTPError(RuntimeError):
    pass


class UnknownHostKeyError(SFTPError):
    """Raised when a server key needs an explicit trust decision from the user."""

    def __init__(self, hostname: str, key) -> None:
        self.hostname = hostname
        self.key = key
        digest = hashlib.sha256(key.asbytes()).digest()
        self.fingerprint = "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")
        self.algorithm = key.get_name()
        super().__init__(f"The authenticity of {hostname} has not been established ({self.fingerprint}).")


@dataclass(frozen=True)
class RemoteEntry:
    name: str
    path: str
    is_dir: bool
    size: int
    modified: datetime
    permissions: int


def remote_join(parent: str, name: str) -> str:
    if not name or name in {".", ".."} or "/" in name or "\x00" in name:
        raise SFTPError("The server returned an unsafe filename.")
    if parent == "/":
        return "/" + name.lstrip("/")
    return posixpath.normpath(posixpath.join(parent, name))


def safe_local_child(parent: Path, name: str) -> Path:
    """Resolve a server-provided filename without allowing directory traversal."""
    if not name or name in {".", ".."} or "/" in name or "\\" in name or "\x00" in name:
        raise SFTPError("The server returned an unsafe filename.")
    root = parent.expanduser().resolve()
    candidate = root / name
    if candidate.is_symlink():
        raise SFTPError(f"Refusing to overwrite the local symbolic link: {candidate}")
    try:
        candidate.resolve().relative_to(root)
    except ValueError as error:
        raise SFTPError("The server returned a filename outside the download folder.") from error
    return candidate


class SFTPService:
    """Persistent Paramiko SSH/SFTP connection used by one background worker."""

    def __init__(self, profile: ConnectionProfile, password: str = "") -> None:
        self.profile = profile
        self.password = password
        self.ssh = None
        self.sftp = None

    @property
    def connected(self) -> bool:
        if self.ssh is None or self.sftp is None:
            return False
        transport = self.ssh.get_transport()
        return bool(transport and transport.is_active())

    def connect(self) -> None:
        self.close()
        try:
            paramiko = importlib.import_module("paramiko")
        except ImportError as error:
            raise SFTPError("python3-paramiko is not installed.") from error

        ensure_app_dirs()
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        try:
            client.load_host_keys(str(KNOWN_HOSTS_FILE))
        except (OSError, ValueError):
            pass

        class ConfirmHostKeyPolicy(paramiko.MissingHostKeyPolicy):
            def missing_host_key(self, _client, hostname, key):
                raise UnknownHostKeyError(hostname, key)

        client.set_missing_host_key_policy(ConfirmHostKeyPolicy())

        socket = None
        if self.profile.jump_host:
            destination = f"{shlex.quote(self.profile.host)}:{self.profile.port}"
            proxy_command = f"ssh -W {destination} {shlex.quote(self.profile.jump_host)}"
            socket = paramiko.ProxyCommand(proxy_command)

        key_path = os.path.expanduser(self.profile.key_path) if self.profile.key_path else None
        try:
            client.connect(
                hostname=self.profile.host,
                port=self.profile.port,
                username=self.profile.username,
                password=self.password or None,
                key_filename=key_path,
                allow_agent=self.profile.use_agent,
                look_for_keys=self.profile.use_agent,
                timeout=15,
                banner_timeout=15,
                auth_timeout=20,
                sock=socket,
                disabled_algorithms={
                    "keys": ["ssh-rsa"],
                    "pubkeys": ["ssh-rsa"],
                },
            )
            transport = client.get_transport()
            if transport:
                transport.set_keepalive(30)
            self.ssh = client
            self.sftp = client.open_sftp()
            client.save_host_keys(str(KNOWN_HOSTS_FILE))
        except UnknownHostKeyError:
            client.close()
            raise
        except Exception as error:
            client.close()
            raise SFTPError(self._friendly_error(error)) from error

    def trust_host_key(self, unknown: UnknownHostKeyError) -> None:
        """Persist a key only after the UI has obtained explicit user approval."""
        try:
            paramiko = importlib.import_module("paramiko")
            ensure_app_dirs()
            host_keys = paramiko.HostKeys()
            try:
                host_keys.load(str(KNOWN_HOSTS_FILE))
            except (OSError, ValueError):
                pass
            host_keys.add(unknown.hostname, unknown.algorithm, unknown.key)
            host_keys.save(str(KNOWN_HOSTS_FILE))
            os.chmod(KNOWN_HOSTS_FILE, 0o600)
        except Exception as error:
            raise SFTPError(f"Could not save the trusted host key: {self._friendly_error(error)}") from error

    def close(self) -> None:
        if self.sftp is not None:
            try:
                self.sftp.close()
            except Exception:
                pass
        if self.ssh is not None:
            try:
                self.ssh.close()
            except Exception:
                pass
        self.sftp = None
        self.ssh = None

    def list_dir(self, path: str) -> tuple[str, list[RemoteEntry]]:
        sftp = self._require_connection()
        try:
            actual_path = sftp.normalize(path or ".")
            attributes = sftp.listdir_attr(actual_path)
        except Exception as error:
            raise SFTPError(self._friendly_error(error)) from error
        entries = [
            RemoteEntry(
                name=item.filename,
                path=remote_join(actual_path, item.filename),
                is_dir=stat.S_ISDIR(item.st_mode),
                size=int(item.st_size or 0),
                modified=datetime.fromtimestamp(item.st_mtime or 0),
                permissions=int(item.st_mode or 0),
            )
            for item in attributes
            if item.filename not in {".", ".."}
        ]
        entries.sort(key=lambda item: (not item.is_dir, item.name.casefold()))
        return actual_path, entries

    def upload(self, local_path: Path, remote_dir: str, progress: ProgressCallback | None = None) -> None:
        local_path = local_path.expanduser().resolve()
        if not local_path.exists():
            raise SFTPError(f"Local path does not exist: {local_path}")
        destination = remote_join(remote_dir, local_path.name)
        try:
            if local_path.is_dir():
                self._upload_directory(local_path, destination, progress)
            else:
                self._require_connection().put(str(local_path), destination, callback=progress)
        except SFTPError:
            raise
        except Exception as error:
            raise SFTPError(self._friendly_error(error)) from error

    def download(
        self,
        entry: RemoteEntry,
        local_dir: Path,
        progress: ProgressCallback | None = None,
        overwrite: bool = False,
    ) -> None:
        local_dir = local_dir.expanduser().resolve()
        local_dir.mkdir(parents=True, exist_ok=True)
        destination = safe_local_child(local_dir, entry.name)
        try:
            if entry.is_dir:
                if destination.exists() and not destination.is_dir():
                    raise SFTPError(f"A local file already exists at {destination}.")
                if destination.exists() and not overwrite:
                    raise SFTPError(f"A local folder named {entry.name} already exists.")
                self._download_directory(entry.path, destination, progress, overwrite)
            else:
                if destination.exists() and not overwrite:
                    raise SFTPError(f"A local file named {entry.name} already exists.")
                if destination.is_dir():
                    raise SFTPError(f"A local folder already exists at {destination}.")
                self._require_connection().get(entry.path, str(destination), callback=progress)
        except SFTPError:
            raise
        except Exception as error:
            raise SFTPError(self._friendly_error(error)) from error

    def mkdir(self, parent: str, name: str) -> None:
        if not name or "/" in name or name in {".", ".."}:
            raise SFTPError("Enter a folder name without slashes.")
        try:
            self._require_connection().mkdir(remote_join(parent, name))
        except Exception as error:
            raise SFTPError(self._friendly_error(error)) from error

    def rename(self, entry: RemoteEntry, new_name: str) -> None:
        if not new_name or "/" in new_name or new_name in {".", ".."}:
            raise SFTPError("Enter a name without slashes.")
        target = remote_join(posixpath.dirname(entry.path), new_name)
        try:
            self._require_connection().rename(entry.path, target)
        except Exception as error:
            raise SFTPError(self._friendly_error(error)) from error

    def delete(self, entries: Iterable[RemoteEntry]) -> None:
        try:
            for entry in entries:
                if entry.is_dir:
                    self._remove_directory(entry.path)
                else:
                    self._require_connection().remove(entry.path)
        except Exception as error:
            raise SFTPError(self._friendly_error(error)) from error

    def _upload_directory(self, local_dir: Path, remote_dir: str, progress: ProgressCallback | None) -> None:
        sftp = self._require_connection()
        try:
            sftp.mkdir(remote_dir)
        except OSError:
            pass
        for child in local_dir.iterdir():
            remote_child = remote_join(remote_dir, child.name)
            if child.is_dir():
                self._upload_directory(child, remote_child, progress)
            else:
                sftp.put(str(child), remote_child, callback=progress)

    def _download_directory(
        self,
        remote_dir: str,
        local_dir: Path,
        progress: ProgressCallback | None,
        overwrite: bool,
    ) -> None:
        sftp = self._require_connection()
        local_dir.mkdir(parents=True, exist_ok=True)
        for item in sftp.listdir_attr(remote_dir):
            remote_child = remote_join(remote_dir, item.filename)
            local_child = safe_local_child(local_dir, item.filename)
            if stat.S_ISDIR(item.st_mode):
                if local_child.exists() and not local_child.is_dir():
                    raise SFTPError(f"A local file already exists at {local_child}.")
                self._download_directory(remote_child, local_child, progress, overwrite)
            else:
                if local_child.exists() and not overwrite:
                    raise SFTPError(f"A local file named {item.filename} already exists.")
                if local_child.is_dir():
                    raise SFTPError(f"A local folder already exists at {local_child}.")
                sftp.get(remote_child, str(local_child), callback=progress)

    def _remove_directory(self, remote_dir: str) -> None:
        sftp = self._require_connection()
        for item in sftp.listdir_attr(remote_dir):
            child = remote_join(remote_dir, item.filename)
            if stat.S_ISDIR(item.st_mode):
                self._remove_directory(child)
            else:
                sftp.remove(child)
        sftp.rmdir(remote_dir)

    def _require_connection(self):
        if not self.connected:
            self.connect()
        return self.sftp

    @staticmethod
    def _friendly_error(error: Exception) -> str:
        message = str(error).strip()
        name = error.__class__.__name__
        if name == "AuthenticationException":
            return "Authentication failed. Check the username, password, or SSH key."
        if name in {"NoValidConnectionsError", "TimeoutError"}:
            return f"Could not reach the server: {message or name}"
        if name == "BadHostKeyException":
            return "The server host key changed. Check the server before reconnecting."
        return message or name
