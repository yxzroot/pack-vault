from io import BytesIO
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from features import (apply_profile, download_modrinth_pack, enabled_zip_names, latest_modrinth_version,
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

    def test_update_matches_installed_hash_and_game_version(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "installed.zip"
            path.write_bytes(b"original zip bytes")
            digest = hashlib.sha512(path.read_bytes()).hexdigest()
            versions = [
                {"id": "old", "version_number": "1", "date_published": "2025-01-01",
                 "game_versions": ["1.8.9"], "files": [{"hashes": {"sha512": digest}}]},
                {"id": "new", "version_number": "2", "date_published": "2026-01-01",
                 "game_versions": ["1.8.9"], "files": [{"filename": "new.zip", "primary": True,
                     "hashes": {"sha512": "a" * 128}, "url": "https://cdn.modrinth.com/data/new.zip"}]},
            ]
            responses = [json.dumps({"project_type": "resourcepack"}).encode(), json.dumps(versions).encode()]
            with patch("features.urlopen", side_effect=lambda request, timeout: BytesIO(responses.pop(0))):
                result = latest_modrinth_version("cool", installed_file=path, game_version="1.8.9")
            self.assertEqual(result["installed_id"], "old")
            self.assertEqual(result["compatible"]["id"], "new")

    def test_download_rejects_invalid_checksum_and_keeps_original(self):
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp)
            (library / "old.zip").write_bytes(b"original")
            zip_bytes = BytesIO()
            with zipfile.ZipFile(zip_bytes, "w") as archive:
                archive.writestr("pack.mcmeta", '{"pack":{"pack_format":1}}')
            raw = zip_bytes.getvalue()
            class Response(BytesIO):
                def geturl(self):
                    return "https://cdn.modrinth.com/data/project/new.zip"
            file = {"filename": "new.zip", "url": "https://cdn.modrinth.com/data/project/new.zip",
                    "hashes": {"sha512": "f" * 128}}
            with patch("features.urlopen", return_value=Response(raw)):
                with self.assertRaisesRegex(ValueError, "checksum"):
                    download_modrinth_pack(file, library, "2")
            self.assertFalse((library / "new.zip").exists())
            file["hashes"]["sha512"] = hashlib.sha512(raw).hexdigest()
            with patch("features.urlopen", return_value=Response(raw)):
                result = download_modrinth_pack(file, library, "2")
            self.assertEqual(result.read_bytes(), raw)
            self.assertEqual((library / "old.zip").read_bytes(), b"original")

    def test_download_rejects_http_redirect_and_invalid_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp)
            archive_bytes = BytesIO()
            with zipfile.ZipFile(archive_bytes, "w") as archive:
                archive.writestr("pack.mcmeta", "[]")
            raw = archive_bytes.getvalue()
            file = {"filename": "update.zip", "url": "https://cdn.modrinth.com/data/pack.zip",
                    "hashes": {"sha512": hashlib.sha512(raw).hexdigest()}}
            class Redirect(BytesIO):
                def geturl(self):
                    return "http://cdn.modrinth.com/data/pack.zip"
            with patch("features.urlopen", return_value=Redirect(raw)):
                with self.assertRaisesRegex(ValueError, "redirected"):
                    download_modrinth_pack(file, library, "1")
            self.assertFalse((library / "update.zip").exists())
            class Response(BytesIO):
                def geturl(self):
                    return "https://cdn.modrinth.com/data/pack.zip"
            with patch("features.urlopen", return_value=Response(raw)):
                with self.assertRaisesRegex(ValueError, "pack.mcmeta"):
                    download_modrinth_pack(file, library, "1")
            self.assertFalse((library / "update.zip").exists())


if __name__ == "__main__":
    unittest.main()
