import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from app import (app_directories, default_pack_folder, discover_clients, import_pack,
                 install_from_library, list_packs, pack_path, toggle)


class PackTests(unittest.TestCase):
    def test_zip_and_toggle(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with zipfile.ZipFile(folder / "Test.zip", "w") as archive:
                archive.writestr("pack.mcmeta", json.dumps({"pack": {"description": "Hello", "pack_format": 1}}))
            self.assertEqual(list_packs(folder)[0]["description"], "Hello")
            toggle(folder, "Test.zip")
            self.assertFalse(list_packs(folder)[0]["enabled"])
            toggle(folder, "Test.zip.disabled")
            self.assertTrue((folder / "Test.zip").exists())

    def test_broken_pack_does_not_crash_listing(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "broken.zip").write_text("not a zip")
            self.assertEqual(list_packs(folder)[0]["description"], "Could not read pack metadata")

    def test_rejects_paths_and_collisions(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for name in ("../escape", "/tmp/escape", "a\\b", "C:\\escape", "a:b.zip", ""):
                with self.assertRaises(ValueError):
                    pack_path(folder, name)
            (folder / "a.zip").touch()
            (folder / "a.zip.disabled").touch()
            with self.assertRaises(ValueError):
                toggle(folder, "a.zip")

    def test_oneclient_style_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "resourcepacks"
            folder.mkdir()
            actual = Path(temp) / "stored.zip"
            with zipfile.ZipFile(actual, "w") as archive:
                archive.writestr("pack.mcmeta", '{"pack":{"description":"Linked"}}')
            try:
                (folder / "linked.zip").symlink_to(actual)
            except OSError as exc:
                self.skipTest(f"Symlink creation unavailable: {exc}")
            self.assertEqual(list_packs(folder)[0]["description"], "Linked")
            toggle(folder, "linked.zip")
            self.assertTrue(actual.exists())
            self.assertTrue((folder / "linked.zip.disabled").is_symlink())

    def test_import_to_library_links_to_oneclient(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "Downloads" / "Cool.zip"
            source.parent.mkdir()
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("pack.mcmeta", '{"pack":{"description":"Cool"}}')
            folder = base / "resourcepacks"
            library = base / "pack-vault" / "packs"
            import_pack(source, folder, library)
            self.assertTrue((library / "Cool.zip").is_file())
            self.assertTrue((folder / "Cool.zip").is_file())
            self.assertEqual(list_packs(folder)[0]["description"], "Cool")
            with self.assertRaises(ValueError):
                import_pack(source, folder, library)
            another = base / "another-client" / "resourcepacks"
            install_from_library("Cool.zip", another, library)
            self.assertTrue((another / "Cool.zip").is_file())
            with self.assertRaises(ValueError):
                install_from_library("Cool.zip", another, library)

    def test_discovery_includes_existing_game_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / ".minecraft").mkdir()
            clients = discover_clients(home, system="Linux", environ={})
            self.assertIn(("Minecraft (vanilla)", home / ".minecraft/resourcepacks"), clients)
            self.assertFalse((home / ".minecraft/resourcepacks").exists())

    def test_windows_and_macos_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            roaming = home / "Roaming"
            local = home / "Local"
            env = {"APPDATA": str(roaming), "LOCALAPPDATA": str(local)}
            data, config = app_directories(home, "Windows", env)
            self.assertEqual(data, local / "PackVault")
            self.assertEqual(config, roaming / "PackVault")
            self.assertEqual(default_pack_folder(home, "Windows", env), roaming / ".minecraft/resourcepacks")
            (roaming / ".minecraft").mkdir(parents=True)
            self.assertIn(("Minecraft (vanilla)", roaming / ".minecraft/resourcepacks"),
                          discover_clients(home, "Windows", env))
            data, config = app_directories(home, "Darwin", {})
            self.assertEqual(data, home / "Library/Application Support/PackVault")
            self.assertEqual(config, data)
            self.assertEqual(default_pack_folder(home, "Darwin", {}),
                             home / "Library/Application Support/minecraft/resourcepacks")
            (home / "Library/Application Support/minecraft").mkdir(parents=True)
            self.assertIn(("Minecraft (vanilla)", home / "Library/Application Support/minecraft/resourcepacks"),
                          discover_clients(home, "Darwin", {}))

    def test_windows_without_symlink_privilege_copies(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            library = base / "library"
            library.mkdir()
            with zipfile.ZipFile(library / "Pack.zip", "w") as archive:
                archive.writestr("pack.mcmeta", '{"pack":{"description":"Pack"}}')
            with patch("app.platform.system", return_value="Windows"), patch.object(
                    Path, "symlink_to", side_effect=PermissionError("symlink privilege required")):
                install_from_library("Pack.zip", base / "client", library)
            installed = base / "client/Pack.zip"
            self.assertFalse(installed.is_symlink())
            self.assertEqual(installed.read_bytes(), (library / "Pack.zip").read_bytes())


if __name__ == "__main__":
    unittest.main()
