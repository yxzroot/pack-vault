import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from compatibility import (FORMATS, convert_pack, detect_game_version, pack_format,
                           pack_supports, texture_previews, version_from_text)
from game_options import read_order, write_order


class CompatibilityTests(unittest.TestCase):
    def test_detect_oneclient_and_vanilla_versions(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            game = base / "OneClient/.minecraft"
            game.mkdir(parents=True)
            (base / "OneClient/metadata/versions/1.8.9-0.19.5").mkdir(parents=True)
            self.assertEqual(detect_game_version(game / "resourcepacks"), "1.8.9")
            other = base / "vanilla/.minecraft"
            other.mkdir(parents=True)
            (other / "launcher_profiles.json").write_text(json.dumps({
                "selectedProfile": "selected", "profiles": {"selected": {"lastVersionId": "1.20.4"}}}))
            self.assertEqual(detect_game_version(other / "resourcepacks"), "1.20.4")
            self.assertEqual(FORMATS["1.8.9"], 1)

    def test_other_releases_and_launchers_are_not_tied_to_oneclient(self):
        self.assertEqual(FORMATS["1.20.3"], 22)
        self.assertEqual(FORMATS["1.18.2"], 8)
        self.assertEqual(FORMATS["1.21.9"], 69.0)
        self.assertEqual(version_from_text("Minecraft 1.20.3 Fabric"), "1.20.3")
        self.assertEqual(version_from_text("1.8.9-0.19.5"), "1.8.9")
        self.assertIsNone(version_from_text("1.20.99"))
        with tempfile.TemporaryDirectory() as temp:
            prism = Path(temp) / "prism"
            prism.mkdir()
            (prism / "mmc-pack.json").write_text(json.dumps({"components": [
                {"uid": "net.fabricmc.fabric-loader", "version": "0.16.3"},
                {"uid": "net.minecraft", "version": "1.20.3"}]}))
            self.assertEqual(detect_game_version(prism / ".minecraft/resourcepacks"), "1.20.3")
            modrinth = Path(temp) / "modrinth"
            modrinth.mkdir()
            (modrinth / "profile.json").write_text(json.dumps({"game_version": "1.21.5"}))
            self.assertEqual(detect_game_version(modrinth / "resourcepacks"), "1.21.5")

    def test_conversion_is_new_copy_and_aliases_legacy_textures(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "Legacy.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("pack.mcmeta", '{"pack":{"pack_format":1,"description":"old"}}')
                archive.writestr("assets/minecraft/textures/blocks/stone.png", b"stone")
                archive.writestr("assets/minecraft/textures/items/diamond_sword.png", b"item")
                archive.writestr("assets/minecraft/models/item/sword.json", b'{}')
                archive.writestr("assets/", b"")
            report = {}
            dest = convert_pack(source, "1.14.4", base / "library", report=report)
            self.assertEqual(pack_format(dest), 4)
            self.assertEqual(report["source_format"], 1)
            self.assertEqual(report["target_format"], 4)
            self.assertEqual(len(report["aliases"]), 2)
            self.assertEqual(report["unchanged"]["models"], 1)
            self.assertEqual(pack_format(source), 1)
            with zipfile.ZipFile(dest) as archive:
                self.assertEqual(archive.read("assets/minecraft/textures/block/stone.png"), b"stone")
                self.assertEqual(archive.read("assets/minecraft/textures/item/diamond_sword.png"), b"item")
                self.assertEqual(archive.read("assets/minecraft/textures/blocks/stone.png"), b"stone")
            with self.assertRaises(ValueError):
                convert_pack(source, "1.14.4", base / "library")
            reversed_pack = convert_pack(dest, "1.8.9", base / "downgrades")
            self.assertEqual(pack_format(reversed_pack), 1)
            modern = convert_pack(source, "1.21.9", base / "modern")
            with zipfile.ZipFile(modern) as archive:
                metadata = json.loads(archive.read("pack.mcmeta"))["pack"]
            self.assertEqual(metadata["min_format"], [69, 0])
            self.assertEqual(metadata["max_format"], [69, 0])
            self.assertNotIn("pack_format", metadata)
            self.assertEqual(pack_format(modern), 69)
            self.assertTrue(pack_supports(modern, "1.21.9"))
            recent = convert_pack(modern, "26.3", base / "recent")
            with zipfile.ZipFile(recent) as archive:
                recent_meta = json.loads(archive.read("pack.mcmeta"))["pack"]
            self.assertEqual(recent_meta["min_format"], [97, 1])
            self.assertEqual(pack_format(recent), "97.1")
            self.assertTrue(pack_supports(recent, "26.3"))

    def test_supported_format_range_is_not_falsely_warned(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "Multi.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("pack.mcmeta", json.dumps({"pack": {
                    "pack_format": 18, "supported_formats": [18, 22]}}))
            self.assertTrue(pack_supports(source, "1.20.4"))
            self.assertFalse(pack_supports(source, "1.21.1"))
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("pack.mcmeta", json.dumps({"pack": {
                    "min_format": [97], "max_format": 97}}))
            self.assertTrue(pack_supports(source, "26.3"))

    def test_preview_reads_samples_without_extracting(self):
        with tempfile.TemporaryDirectory() as temp:
            zip_path = Path(temp) / "Example.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("pack.png", b"fake png")
                archive.writestr("assets/minecraft/textures/blocks/stone.png", b"stone")
            self.assertEqual(len(texture_previews(zip_path)), 2)
            self.assertEqual(list(Path(temp).iterdir()), [zip_path])

    def test_bad_metadata_does_not_crash_cards_or_leave_converted_file(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "Broken.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("pack.mcmeta", "[]")
            self.assertIsNone(pack_format(source))
            with self.assertRaisesRegex(ValueError, "metadata"):
                convert_pack(source, "1.20.4", base / "library")
            self.assertFalse((base / "library").exists())

    def test_options_order_backup_and_oneclient_legacy_field(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "game/resourcepacks"
            folder.mkdir(parents=True)
            (folder / "A.zip").touch()
            (folder / "B.zip").touch()
            options = folder.parent / "options.txt"
            options.write_bytes(b"music:1\r\nresourcePacks:[\"A.zip\"]\r\noneconfig_legacy_resourcePacks:[\"A.zip\"]\r\nother:leave-me\r\n")
            self.assertEqual(read_order(folder), ["A.zip"])
            backup = write_order(folder, ["B.zip", "A.zip"])
            self.assertIn(b"resourcePacks:[\"B.zip\",\"A.zip\"]\r\n", options.read_bytes())
            self.assertIn(b"oneconfig_legacy_resourcePacks:[\"B.zip\",\"A.zip\"]", options.read_bytes())
            self.assertIn(b"other:leave-me\r\n", options.read_bytes())
            self.assertEqual(backup.read_bytes(),
                             b"music:1\r\nresourcePacks:[\"A.zip\"]\r\noneconfig_legacy_resourcePacks:[\"A.zip\"]\r\nother:leave-me\r\n")
            with self.assertRaises(ValueError):
                write_order(folder, ["Missing.zip"])
            self.assertIsNone(write_order(folder, ["B.zip", "A.zip"]))

    def test_order_keeps_builtin_packs_and_refuses_missing_zip(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "game/resourcepacks"
            folder.mkdir(parents=True)
            for name in ("A.zip", "B.zip"):
                (folder / name).touch()
            options = folder.parent / "options.txt"
            options.write_text('resourcePacks:["vanilla","file/A.zip","programmer_art","file/B.zip"]\n')
            self.assertEqual(read_order(folder), ["A.zip", "B.zip"])
            write_order(folder, ["B.zip", "A.zip"])
            self.assertEqual(json.loads(options.read_text().split(":", 1)[1]),
                             ["vanilla", "file/B.zip", "programmer_art", "file/A.zip"])
            options.write_text('resourcePacks:["vanilla","file/Missing.zip","programmer_art"]\n')
            with self.assertRaisesRegex(ValueError, "unavailable"):
                read_order(folder)
            with self.assertRaisesRegex(ValueError, "unavailable"):
                write_order(folder, ["A.zip"])
            self.assertEqual(options.read_text(),
                             'resourcePacks:["vanilla","file/Missing.zip","programmer_art"]\n')
