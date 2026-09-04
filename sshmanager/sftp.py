from __future__ import annotations

import importlib
import base64
import hashlib
import os
import posixpath
import shlex
import stat
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from .config import KNOWN_HOSTS_FILE, ensure_app_dirs
from .models import ConnectionProfile

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


@dataclass(frozen=True)
class TransferProgress:
    direction: str
    current_name: str
    current_transferred: int
    current_size: int
    completed_files: int
    total_files: int
    transferred_bytes: int
    total_bytes: int
    elapsed: float


@dataclass(frozen=True)
class TransferSummary:
    direction: str
    files: int
    bytes: int
    elapsed: float


@dataclass(frozen=True)
class _TransferItem:
    source: str
    destination: str
    display_name: str
    size: int


ProgressCallback = Callable[[TransferProgress], None]


class _TransferTracker:
    def __init__(self, direction: str, items: list[_TransferItem], callback: ProgressCallback | None) -> None:
        self.direction = direction
        self.items = items
        self.callback = callback
        self.started = time.monotonic()
        self.total_bytes = sum(item.size for item in items)
        self.transferred = [0] * len(items)
        self.completed: set[int] = set()
        self.lock = threading.Lock()

    def emit_initial(self) -> None:
        if self.callback:
            self.callback(self._snapshot("", 0, 0))

    def update(self, index: int, transferred: int, total: int) -> None:
        with self.lock:
            item = self.items[index]
            current_size = max(item.size, int(total))
            current = max(0, min(int(transferred), current_size))
            self.transferred[index] = max(self.transferred[index], current)
            snapshot = self._snapshot(item.display_name, current, current_size)
        if self.callback:
            self.callback(snapshot)

    def finish(self, index: int) -> None:
        with self.lock:
            item = self.items[index]
            self.transferred[index] = item.size
            self.completed.add(index)
            snapshot = self._snapshot(item.display_name, item.size, item.size)
        if self.callback:
            self.callback(snapshot)

    def summary(self) -> TransferSummary:
        return TransferSummary(self.direction, len(self.items), self.total_bytes, time.monotonic() - self.started)

    def _snapshot(self, name: str, current: int, current_size: int) -> TransferProgress:
        return TransferProgress(
            direction=self.direction,
            current_name=name,
            current_transferred=current,
            current_size=current_size,
            completed_files=len(self.completed),
            total_files=len(self.items),
            transferred_bytes=sum(self.transferred),
            total_bytes=self.total_bytes,
            elapsed=time.monotonic() - self.started,
        )


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
        self.upload_many([local_path], remote_dir, progress)

    def upload_many(
        self,
        local_paths: Iterable[Path],
        remote_dir: str,
        progress: ProgressCallback | None = None,
    ) -> TransferSummary:
        try:
            directories: list[str] = []
            items: list[_TransferItem] = []
            for requested_path in local_paths:
                local_path = requested_path.expanduser().resolve()
                if not local_path.exists():
                    raise SFTPError(f"Local path does not exist: {local_path}")
                destination = remote_join(remote_dir, local_path.name)
                if local_path.is_dir():
                    self._plan_upload_directory(local_path, destination, local_path.name, directories, items)
                else:
                    items.append(_TransferItem(str(local_path), destination, local_path.name, local_path.stat().st_size))

            sftp = self._require_connection()
            for directory in directories:
                self._ensure_remote_directory(sftp, directory)
            return self._transfer_items("Uploading", items, progress, self._upload_item)
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
        self.download_many([entry], local_dir, progress, overwrite)

    def download_many(
        self,
        entries: Iterable[RemoteEntry],
        local_dir: Path,
        progress: ProgressCallback | None = None,
        overwrite: bool = False,
    ) -> TransferSummary:
        local_dir = local_dir.expanduser().resolve()
        local_dir.mkdir(parents=True, exist_ok=True)
        try:
            prepared: list[tuple[RemoteEntry, Path]] = []
            for entry in entries:
                destination = safe_local_child(local_dir, entry.name)
                if entry.is_dir:
                    if destination.exists() and not destination.is_dir():
                        raise SFTPError(f"A local file already exists at {destination}.")
                    if destination.exists() and not overwrite:
                        raise SFTPError(f"A local folder named {entry.name} already exists.")
                else:
                    self._validate_download_destination(destination, entry.name, overwrite)
                prepared.append((entry, destination))

            sftp = self._require_connection()
            directories: list[Path] = []
            items: list[_TransferItem] = []
            for entry, destination in prepared:
                if entry.is_dir:
                    self._plan_download_directory(
                        sftp, entry.path, destination, entry.name, directories, items, overwrite
                    )
                else:
                    items.append(_TransferItem(entry.path, str(destination), entry.name, entry.size))

            for directory in directories:
                directory.mkdir(parents=True, exist_ok=True)
            return self._transfer_items("Downloading", items, progress, self._download_item)
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

    def _plan_upload_directory(
        self,
        local_dir: Path,
        remote_dir: str,
        display_dir: str,
        directories: list[str],
        items: list[_TransferItem],
    ) -> None:
        directories.append(remote_dir)
        for child in sorted(local_dir.iterdir(), key=lambda path: path.name.casefold()):
            remote_child = remote_join(remote_dir, child.name)
            display_name = posixpath.join(display_dir, child.name)
            if child.is_dir():
                self._plan_upload_directory(child, remote_child, display_name, directories, items)
            else:
                items.append(_TransferItem(str(child), remote_child, display_name, child.stat().st_size))

    def _plan_download_directory(
        self,
        sftp,
        remote_dir: str,
        local_dir: Path,
        display_dir: str,
        directories: list[Path],
        items: list[_TransferItem],
        overwrite: bool,
    ) -> None:
        directories.append(local_dir)
        for item in sftp.listdir_attr(remote_dir):
            if item.filename in {".", ".."}:
                continue
            remote_child = remote_join(remote_dir, item.filename)
            local_child = safe_local_child(local_dir, item.filename)
            display_name = posixpath.join(display_dir, item.filename)
            if stat.S_ISDIR(item.st_mode):
                if local_child.exists() and not local_child.is_dir():
                    raise SFTPError(f"A local file already exists at {local_child}.")
                self._plan_download_directory(
                    sftp, remote_child, local_child, display_name, directories, items, overwrite
                )
            else:
                self._validate_download_destination(local_child, item.filename, overwrite)
                items.append(_TransferItem(remote_child, str(local_child), display_name, int(item.st_size or 0)))

    @staticmethod
    def _validate_download_destination(destination: Path, name: str, overwrite: bool) -> None:
        if destination.exists() and not overwrite:
            raise SFTPError(f"A local file named {name} already exists.")
        if destination.is_dir():
            raise SFTPError(f"A local folder already exists at {destination}.")

    @staticmethod
    def _ensure_remote_directory(sftp, directory: str) -> None:
        try:
            sftp.mkdir(directory)
        except OSError as mkdir_error:
            try:
                attributes = sftp.stat(directory)
            except OSError:
                raise mkdir_error
            if not stat.S_ISDIR(attributes.st_mode):
                raise SFTPError(f"A remote file already exists at {directory}.")

    @staticmethod
    def _upload_item(sftp, item: _TransferItem, callback: Callable[[int, int], None]) -> None:
        # SFTP writes are already acknowledged. Skipping Paramiko's additional
        # post-upload stat removes one network round trip for every small file.
        sftp.put(item.source, item.destination, callback=callback, confirm=False)

    @staticmethod
    def _download_item(sftp, item: _TransferItem, callback: Callable[[int, int], None]) -> None:
        sftp.get(
            item.source,
            item.destination,
            callback=callback,
            prefetch=True,
            max_concurrent_prefetch_requests=64,
        )

    def _transfer_items(
        self,
        direction: str,
        items: list[_TransferItem],
        progress: ProgressCallback | None,
        operation: Callable,
    ) -> TransferSummary:
        tracker = _TransferTracker(direction, items, progress)
        tracker.emit_initial()
        if not items:
            return tracker.summary()

        primary = self._require_connection()
        clients = [primary]
        for _index in range(min(4, len(items)) - 1):
            try:
                clients.append(self.ssh.open_sftp())
            except Exception:
                break

        batches = [items[index::len(clients)] for index in range(len(clients))]
        item_indexes = {id(item): index for index, item in enumerate(items)}

        def transfer_batch(client, batch: list[_TransferItem]) -> None:
            for item in batch:
                index = item_indexes[id(item)]
                operation(client, item, lambda done, total, i=index: tracker.update(i, done, total))
                tracker.finish(index)

        try:
            with ThreadPoolExecutor(max_workers=len(clients), thread_name_prefix="sftp-transfer") as pool:
                futures = [pool.submit(transfer_batch, client, batch) for client, batch in zip(clients, batches)]
                for future in futures:
                    future.result()
        finally:
            for client in clients[1:]:
                try:
                    client.close()
                except Exception:
                    pass
        return tracker.summary()

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
