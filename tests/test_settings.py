import json
import tempfile
import unittest
from pathlib import Path

from sshmanager.settings import AppSettings, DEFAULT_THEME, SettingsStore


class SettingsStoreTests(unittest.TestCase):
    def test_missing_or_invalid_settings_use_dark_theme(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = SettingsStore(path)
            self.assertEqual(store.load().theme, DEFAULT_THEME)
            path.write_text('{"theme": "unknown"}', encoding="utf-8")
            self.assertEqual(store.load().theme, DEFAULT_THEME)

    def test_round_trip_uses_private_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = SettingsStore(path)
            store.save(AppSettings(theme="light"))
            self.assertEqual(store.load().theme, "light")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"theme": "light"})

    def test_loading_repairs_permissive_settings_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"theme": "light"}', encoding="utf-8")
            path.chmod(0o644)
            SettingsStore(path).load()
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
