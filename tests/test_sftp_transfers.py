import stat
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from sshmanager.models import ConnectionProfile
from sshmanager.sftp import RemoteEntry, SFTPService
from sshmanager.sftp_browser import SFTPBrowserWidget, format_duration


class _FakeTransport:
    @staticmethod
    def is_active():
        return True


class _FakeSFTP:
    def __init__(self, shared):
        self.shared = shared

    def mkdir(self, path):
        self.shared["directories"].append(path)

    @staticmethod
    def stat(_path):
        return SimpleNamespace(st_mode=stat.S_IFDIR | 0o755)

    def put(self, source, destination, callback, confirm):
        size = Path(source).stat().st_size
        self._enter()
        try:
            callback(size // 2, size)
            time.sleep(0.03)
            callback(size, size)
            self.shared["uploads"].append((destination, confirm))
        finally:
            self._leave()

    def get(self, source, destination, callback, prefetch, max_concurrent_prefetch_requests):
        size = 8
        self._enter()
        try:
            callback(size // 2, size)
            time.sleep(0.03)
            Path(destination).write_bytes(b"download")
            callback(size, size)
            self.shared["downloads"].append(
                (source, prefetch, max_concurrent_prefetch_requests)
            )
        finally:
            self._leave()

    def close(self):
        self.shared["closed"] += 1

    def _enter(self):
        with self.shared["lock"]:
            self.shared["active"] += 1
            self.shared["max_active"] = max(self.shared["max_active"], self.shared["active"])

    def _leave(self):
        with self.shared["lock"]:
            self.shared["active"] -= 1


class _FakeSSH:
    def __init__(self, shared):
        self.shared = shared

    @staticmethod
    def get_transport():
        return _FakeTransport()

    def open_sftp(self):
        self.shared["opened"] += 1
        return _FakeSFTP(self.shared)


def _connected_service():
    shared = {
        "active": 0,
        "max_active": 0,
        "opened": 0,
        "closed": 0,
        "uploads": [],
        "downloads": [],
        "directories": [],
        "lock": threading.Lock(),
    }
    service = SFTPService(ConnectionProfile.create("Test"))
    service.ssh = _FakeSSH(shared)
    service.sftp = _FakeSFTP(shared)
    return service, shared


class SFTPTransferTests(unittest.TestCase):
    def test_small_uploads_use_four_channels_without_post_upload_stat(self):
        service, shared = _connected_service()
        progress = []
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "batch"
            folder.mkdir()
            for index in range(8):
                (folder / f"file-{index}.txt").write_bytes(b"data")

            summary = service.upload_many([folder], "/remote", progress.append)

        self.assertEqual(summary.files, 8)
        self.assertEqual(summary.bytes, 32)
        self.assertEqual(len(shared["uploads"]), 8)
        self.assertTrue(all(confirm is False for _destination, confirm in shared["uploads"]))
        self.assertEqual(shared["opened"], 3)
        self.assertEqual(shared["closed"], 3)
        self.assertGreater(shared["max_active"], 1)
        self.assertEqual(progress[-1].completed_files, 8)
        self.assertEqual(progress[-1].transferred_bytes, 32)

    def test_small_downloads_use_parallel_prefetched_channels(self):
        service, shared = _connected_service()
        entries = [
            RemoteEntry(f"file-{index}.txt", f"/remote/file-{index}.txt", False, 8, None, 0)
            for index in range(8)
        ]
        progress = []
        with tempfile.TemporaryDirectory() as directory:
            summary = service.download_many(entries, Path(directory), progress.append)
            self.assertTrue(all((Path(directory) / entry.name).exists() for entry in entries))

        self.assertEqual(summary.files, 8)
        self.assertEqual(len(shared["downloads"]), 8)
        self.assertTrue(all(prefetch is True for _source, prefetch, _limit in shared["downloads"]))
        self.assertTrue(all(limit == 64 for _source, _prefetch, limit in shared["downloads"]))
        self.assertGreater(shared["max_active"], 1)
        self.assertEqual(progress[-1].completed_files, 8)

    def test_refresh_all_updates_both_current_folders(self):
        calls = []
        browser = SimpleNamespace(
            refresh_local=lambda: calls.append("local"),
            refresh_remote=lambda: calls.append("remote"),
        )
        SFTPBrowserWidget.refresh_all(browser)
        self.assertEqual(calls, ["local", "remote"])

    def test_duration_is_readable(self):
        self.assertEqual(format_duration(5), "5s")
        self.assertEqual(format_duration(65), "1m 05s")


if __name__ == "__main__":
    unittest.main()
