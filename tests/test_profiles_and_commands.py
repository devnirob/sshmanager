import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sshmanager.models import ConnectionProfile
from sshmanager.profiles import ProfileStore
from sshmanager.system_ssh import ssh_command


class ProfileStoreTests(unittest.TestCase):
    def test_round_trip_uses_private_atomic_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            store = ProfileStore(path)
            original = ConnectionProfile.create("Database")
            original.host = "db.example.test"
            original.username = "admin"
            store.save([original])
            loaded = store.load()
            self.assertEqual(loaded[0].to_dict(), original.to_dict())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertIsInstance(json.loads(path.read_text()), list)

    def test_loading_repairs_permissive_profile_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            path.write_text("[]", encoding="utf-8")
            path.chmod(0o644)
            ProfileStore(path).load()
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class SSHCommandTests(unittest.TestCase):
    @patch("sshmanager.system_ssh.shutil.which", return_value="/usr/bin/sshpass")
    def test_password_uses_anonymous_fd_not_environment_or_command_line(self, _which):
        profile = ConnectionProfile.create("Server")
        profile.host = "192.0.2.10"
        profile.username = "nirob"
        profile.port = 2222
        profile.jump_host = "jump.example.test"
        command, environment = ssh_command(profile, "secret", password_fd=9)
        self.assertEqual(command[:4], ["sshpass", "-d", "9", "ssh"])
        self.assertNotIn("secret", command)
        self.assertFalse(any(item.startswith("SSHPASS=") for item in environment))
        self.assertIn("-J", command)
        self.assertIn("nirob@192.0.2.10", command)
        self.assertIn("ForwardAgent=no", command)
        self.assertIn("ClearAllForwardings=yes", command)
        self.assertIn("HostKeyAlgorithms=-ssh-rsa", command)


if __name__ == "__main__":
    unittest.main()
