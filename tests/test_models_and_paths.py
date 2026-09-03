import unittest
import tempfile
from pathlib import Path
from datetime import datetime

from sshmanager.models import ConnectionProfile
from sshmanager.sftp import RemoteEntry, SFTPError, SFTPService, UnknownHostKeyError, remote_join, safe_local_child
from sshmanager.sftp_browser import format_size


class ProfileTests(unittest.TestCase):
    def test_old_description_is_migrated_to_notes(self):
        profile = ConnectionProfile.from_dict({
            "id": "abc",
            "name": "Web",
            "host": "10.0.0.8",
            "username": "root",
            "description": "Production",
        })
        self.assertEqual(profile.notes, "Production")
        self.assertEqual(profile.port, 22)

    def test_validation_reports_required_connection_fields(self):
        errors = ConnectionProfile.create().validate()
        self.assertIn("Host or IP address is required.", errors)
        self.assertIn("Username is required.", errors)

    def test_ssh_option_injection_is_rejected(self):
        profile = ConnectionProfile.create("Unsafe")
        profile.host = "-oProxyCommand=bad"
        profile.username = "admin"
        self.assertTrue(any("Host cannot begin" in error for error in profile.validate()))

    def test_invalid_profile_types_are_safely_migrated(self):
        profile = ConnectionProfile.from_dict({"id": 42, "host": [], "username": None})
        self.assertIsInstance(profile.id, str)
        self.assertEqual(profile.host, "")
        self.assertEqual(profile.username, "")


class PathTests(unittest.TestCase):
    def test_remote_join_preserves_root(self):
        self.assertEqual(remote_join("/", "etc"), "/etc")
        self.assertEqual(remote_join("/var/www", "index.html"), "/var/www/index.html")

    def test_remote_join_rejects_traversal(self):
        for name in ("../secret", ".", "..", "/etc/passwd", "bad\x00name"):
            with self.subTest(name=name), self.assertRaises(SFTPError):
                remote_join("/home/user", name)

    def test_download_name_stays_inside_local_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(safe_local_child(root, "report.txt"), root / "report.txt")
            with self.assertRaises(SFTPError):
                safe_local_child(root, "../../.bashrc")

    def test_download_does_not_follow_existing_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "link").symlink_to("/tmp")
            with self.assertRaises(SFTPError):
                safe_local_child(root, "link")

    def test_unknown_host_key_uses_sha256_fingerprint(self):
        class FakeKey:
            @staticmethod
            def asbytes():
                return b"server-key"

            @staticmethod
            def get_name():
                return "ssh-ed25519"

        error = UnknownHostKeyError("example.test", FakeKey())
        self.assertEqual(error.algorithm, "ssh-ed25519")
        self.assertTrue(error.fingerprint.startswith("SHA256:"))

    def test_download_refuses_silent_local_overwrite(self):
        entry = RemoteEntry("report.txt", "/report.txt", False, 10, datetime.now(), 0o644)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / entry.name).write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(SFTPError, "already exists"):
                SFTPService(ConnectionProfile.create()).download(entry, root)

    def test_format_size(self):
        self.assertEqual(format_size(1), "1 B")
        self.assertEqual(format_size(1536), "1.5 KB")


if __name__ == "__main__":
    unittest.main()
