import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from game_options import options_backups, restore_options_backup, write_order
from vault_tools import (duplicate_zips, export_profile, game_running, import_profile,
                         pack_backups, restore_pack_backup)


class VaultToolsTests(unittest.TestCase):
    def test_running_detection_is_client_specific(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "client/resourcepacks"
            folder.mkdir(parents=True)
            matching = MagicMock(info={"name": "javaw.exe", "cmdline": ["javaw", "--gameDir", str(folder.parent)]})
            other = MagicMock(info={"name": "java", "cmdline": ["java", "--gameDir", str(Path(temp) / "other")]})
            with patch("vault_tools.psutil.process_iter", return_value=[other]):
                self.assertFalse(game_running(folder))
            with patch("vault_tools.psutil.process_iter", return_value=[other, matching]):
                self.assertTrue(game_running(folder))

    def test_profile_roundtrip_and_reject_bad_files(self):
        with tempfile.TemporaryDirectory() as temp:
            exported = Path(temp) / "My profile.json"
            entry = {"packs": ["Sword.zip"], "order": ["Sword.zip"]}
            export_profile(exported, "My profile", entry, "1.20.4")
            self.assertEqual(import_profile(exported), ("My profile", entry))
            with self.assertRaises(FileExistsError):
                export_profile(exported, "My profile", entry, "1.20.4")
            exported.write_text(json.dumps({"format": "pack-vault-profile", "version": 1,
                                            "name": "Bad", "packs": ["../oops.zip"], "order": []}))
            with self.assertRaisesRegex(ValueError, "Invalid pack name"):
                import_profile(exported)
            exported.write_text("[1, 2, 3]")
            with self.assertRaisesRegex(ValueError, "not a supported|Not a supported"):
                import_profile(exported)

    def test_duplicate_hashes_skip_symlink_to_library_but_detect_independent_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            library, client = Path(temp) / "library", Path(temp) / "client"
            library.mkdir()
            client.mkdir()
            (library / "A.zip").write_bytes(b"same ZIP bytes")
            (client / "Linked.zip").symlink_to(library / "A.zip")
            (client / "Different.zip").write_bytes(b"same ZIP byteX")
            self.assertEqual(duplicate_zips((library, client)), [])
            (client / "Copy.zip.disabled").write_bytes(b"same ZIP bytes")
            self.assertEqual(duplicate_zips((library, client)), [[library / "A.zip", client / "Copy.zip.disabled"]])
            self.assertEqual(duplicate_zips((library, client), cancelled=lambda: True), [])

    def test_restore_options_preserves_current_as_undo_and_rejects_external_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "client/resourcepacks"
            folder.mkdir(parents=True)
            for name in ("A.zip", "B.zip"):
                (folder / name).touch()
            options = folder.parent / "options.txt"
            original = 'music:1\nresourcePacks:["A.zip"]\n'
            options.write_text(original)
            backup = write_order(folder, ["B.zip"])
            self.assertEqual(options_backups(folder), [backup])
            undo = restore_options_backup(folder, backup)
            self.assertEqual(options.read_text(), original)
            self.assertIn('resourcePacks:["B.zip"]', undo.read_text())
            self.assertEqual(len(options_backups(folder)), 2)
            external = Path(temp) / "outside.txt"
            external.write_text(original)
            with self.assertRaisesRegex(ValueError, "Pack Vault"):
                restore_options_backup(folder, external)
            options.write_text("broken options")
            restore_options_backup(folder, backup)
            self.assertEqual(options.read_text(), original)

    def test_restore_pack_keeps_existing_zip_and_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "client/resourcepacks"
            folder.mkdir(parents=True)
            backups = folder.parent / "pack-vault-backups"
            backups.mkdir()
            (folder / "A.zip").write_bytes(b"current")
            (backups / "A.zip").write_bytes(b"original")
            (backups / "A.zip.1").write_bytes(b"second backup")
            original_folder = backups / "Folder"
            original_folder.mkdir()
            (original_folder / "pack.mcmeta").write_text('{}')
            self.assertEqual(len(pack_backups(folder)), 3)
            restored = restore_pack_backup(folder, backups / "A.zip")
            self.assertEqual(restored.name, "A-restored-1.zip")
            self.assertEqual(restored.read_bytes(), b"original")
            again = restore_pack_backup(folder, backups / "A.zip.1")
            self.assertEqual(again.name, "A-restored-2.zip")
            self.assertEqual((folder / "A.zip").read_bytes(), b"current")
            folder_restored = restore_pack_backup(folder, original_folder)
            self.assertEqual((folder_restored / "pack.mcmeta").read_text(), '{}')
            with self.assertRaisesRegex(ValueError, "Pack Vault"):
                restore_pack_backup(folder, folder / "A.zip")
