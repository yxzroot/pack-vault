from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from features import (apply_profile, enabled_zip_names, latest_modrinth_version,
                      modrinth_slug, scan_conflicts)


def pack(path, assets=()):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("pack.mcmeta", '{"pack":{"description":"Test"}}')
        for asset in assets:
            archive.writestr(asset, b"texture")


class FeatureTests(unittest.TestCase):
    def test_profile_enable_disable_restore_and_missing_pack(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            folder = base / "client" / "resourcepacks"
            library = base / "library"
            folder.mkdir(parents=True)
            library.mkdir()
            pack(folder / "A.zip")
            pack(folder / "B.zip.disabled")
            pack(library / "C.zip")
            before = enabled_zip_names(folder)
            self.assertEqual(before, ["A.zip"])
            with self.assertRaises(ValueError):
                apply_profile(folder, ["Missing.zip"], library)
            self.assertEqual(enabled_zip_names(folder), before)
            changes = apply_profile(folder, ["B.zip", "C.zip"], library)
            self.assertEqual(changes["hidden"], ["A.zip"])
            self.assertEqual(enabled_zip_names(folder), ["B.zip", "C.zip"])
            apply_profile(folder, before, library)
            self.assertEqual(enabled_zip_names(folder), before)
            self.assertTrue((folder / "B.zip.disabled").exists())
            self.assertTrue((folder / "C.zip.disabled").exists())

    def test_profile_rolls_back_when_install_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            folder, library = base / "client", base / "library"
            folder.mkdir()
            library.mkdir()
            pack(folder / "A.zip")
            pack(library / "C.zip")
            with patch("features.place_in_client", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    apply_profile(folder, ["C.zip"], library)
            self.assertEqual(enabled_zip_names(folder), ["A.zip"])
            self.assertFalse((folder / "A.zip.disabled").exists())

    def test_conflicts_only_include_available_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            pack(folder / "A.zip", ["assets/minecraft/textures/stone.png", "assets/minecraft/a.png"])
            pack(folder / "B.zip", ["assets/minecraft/textures/stone.png"])
            pack(folder / "C.zip.disabled", ["assets/minecraft/textures/stone.png"])
            self.assertEqual(scan_conflicts(folder),
                             [("assets/minecraft/textures/stone.png", ["A.zip", "B.zip"])])

    def test_modrinth_only_accepts_resourcepack_projects(self):
        self.assertEqual(modrinth_slug("https://modrinth.com/resourcepack/cool-pack"), "cool-pack")
        for url in ("https://evil.example/resourcepack/cool-pack", "http://modrinth.com/resourcepack/p",
                    "https://modrinth.com/mod/cool-pack", "../oops"):
            with self.assertRaises(ValueError):
                modrinth_slug(url)

        responses = [
            {"project_type": "resourcepack"},
            [{"id": "old", "version_number": "1", "date_published": "2025-01-01"},
             {"id": "new", "version_number": "2", "date_published": "2026-01-01"}],
        ]
        def fake_open(request, timeout):
            self.assertEqual(request.full_url.split("/")[2], "api.modrinth.com")
            return BytesIO(json.dumps(responses.pop(0)).encode())
        with patch("features.urlopen", side_effect=fake_open):
            self.assertEqual(latest_modrinth_version("cool-pack")["id"], "new")


if __name__ == "__main__":
    unittest.main()
