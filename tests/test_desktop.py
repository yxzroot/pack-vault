import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import zipfile

import desktop
from desktop import AnimatedButton, PackVault, THEMES


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_apple_theme_tab_motion_and_click_feedback(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Path(temp) / "settings.json"
            settings.write_text(json.dumps({"tour_complete": True}))
            with patch("desktop.SETTINGS", settings):
                window = PackVault()
                window.show()
                self.app.processEvents()
                self.assertEqual(window.tabs.count(), 5)
                self.assertIn("Apple", THEMES)
                window.version_box.setCurrentIndex(window.version_box.findData("1.20.3"))
                self.assertEqual(window.selected_version(), "1.20.3")
                window.theme_box.setCurrentText("Apple")
                self.assertEqual(json.loads(settings.read_text())["theme"], "Apple")

                window.tabs.setCurrentIndex(1)
                self.assertGreater(window.tabs.widget(1).pos().x(), 0)
                QTest.qWait(790)
                self.assertEqual(window.tabs.widget(1).pos().x(), 0)

                button = next(b for b in window.findChildren(AnimatedButton) if "Surprise" in b.text())
                QTest.mousePress(button, Qt.MouseButton.LeftButton)
                self.assertLess(button._ripple, 1.0)
                window.notify("Done!")
                self.assertIsNotNone(window._toast)
                window.close()

    def test_profiles_and_drag_drop_import(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            folder = base / "client/resourcepacks"
            folder.mkdir(parents=True)
            options = folder.parent / "options.txt"
            options.write_text('resourcePacks:["A.zip"]\noneconfig_legacy_resourcePacks:["A.zip"]\n')
            library = base / "library"
            library.mkdir()
            for path in (folder / "A.zip", library / "B.zip", base / "C.zip"):
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("pack.mcmeta", '{"pack":{"description":"test"}}')
            settings = base / "settings.json"
            settings.write_text(json.dumps({"tour_complete": True, "client": str(folder),
                "custom_clients": [{"name": "Test", "path": str(folder)}],
                "profiles": {str(folder): {"B only": {"packs": ["B.zip"], "order": ["B.zip"]}}}}))
            with patch("desktop.SETTINGS", settings), patch("desktop.DEFAULT_LIBRARY", library):
                window = PackVault()
                window.show()
                window.tabs.setCurrentIndex(3)
                with patch.object(window, "confirm_options_write", return_value=True):
                    window.activate_profile("B only")
                self.assertTrue((folder / "A.zip.disabled").exists())
                self.assertTrue((folder / "B.zip").exists())
                self.assertIn('resourcePacks:["B.zip"]', options.read_text())
                self.assertEqual(json.loads(settings.read_text())["profile_previous"][str(folder)], ["A.zip"])
                with patch.object(window, "confirm_options_write", return_value=True):
                    window.deactivate_profile()
                self.assertTrue((folder / "A.zip").exists())
                self.assertTrue((folder / "B.zip.disabled").exists())
                self.assertIn('resourcePacks:["A.zip"]', options.read_text())

                mime = QMimeData()
                mime.setUrls([QUrl.fromLocalFile(str(base / "C.zip"))])
                class DropEvent:
                    def __init__(self):
                        self.accepted = False

                    def mimeData(self):
                        return mime

                    def acceptProposedAction(self):
                        self.accepted = True

                drag = DropEvent()
                window.dragEnterEvent(drag)
                self.assertTrue(drag.accepted)
                drop = DropEvent()
                window.dropEvent(drop)
                self.assertTrue((folder / "C.zip").is_file())
                self.assertTrue((library / "C.zip").is_file())
                window.tabs.setCurrentIndex(4)
                self.assertEqual(window.order_list.count(), 2)
                with patch.object(window, "confirm_options_write", return_value=True):
                    window.save_order()
                self.assertTrue((folder.parent / "pack-vault-backups").is_dir())
                window.close()

    def test_opt_in_update_check_saves_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Path(temp) / "settings.json"
            settings.write_text(json.dumps({"tour_complete": True}))
            result = {"id": "version-1", "number": "1.0", "url": "https://modrinth.com/resourcepack/cool/versions"}
            with patch("desktop.SETTINGS", settings), patch("desktop.latest_modrinth_version", return_value=result) as lookup:
                window = PackVault()
                window.show()
                window.start_update_check({"Cool.zip": "cool"}, baseline=True)
                for _ in range(20):
                    QTest.qWait(25)
                    if window.update_worker is None:
                        break
                self.assertIsNone(window.update_worker)
                self.assertEqual(json.loads(settings.read_text())["tracked_updates"]["Cool.zip"]["id"], "version-1")
                lookup.assert_called_once_with("cool", installed_file=desktop.DEFAULT_LIBRARY / "Cool.zip",
                                               game_version=window.selected_version())
                window.close()

    def test_update_rollback_restores_selected_original(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            folder = base / "game/resourcepacks"
            folder.mkdir(parents=True)
            library = base / "library"
            library.mkdir()
            for name in ("Old.zip", "New.zip"):
                (folder / name).write_bytes(b"pack")
            options = folder.parent / "options.txt"
            options.write_text('resourcePacks:["New.zip"]\n')
            settings = base / "settings.json"
            settings.write_text(json.dumps({"tour_complete": True, "client": str(folder),
                "custom_clients": [{"name": "Test", "path": str(folder)}],
                "update_rollback": {"New.zip": "Old.zip"}}))
            with patch("desktop.SETTINGS", settings), patch("desktop.DEFAULT_LIBRARY", library):
                window = PackVault()
                with patch.object(window, "confirm_options_write", return_value=True):
                    window.rollback_update("New.zip")
                self.assertEqual(options.read_text(), 'resourcePacks:["Old.zip"]\n')
                self.assertEqual((folder / "New.zip").read_bytes(), b"pack")
                self.assertTrue(list((folder.parent / "pack-vault-backups").glob("options-*.txt")))
                window.close()

    def test_close_waits_for_running_network_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Path(temp) / "settings.json"
            settings.write_text(json.dumps({"tour_complete": True}))
            with patch("desktop.SETTINGS", settings):
                window = PackVault()
                window.show()
                worker = MagicMock()
                worker.isRunning.return_value = True
                window.download_worker = worker
                with patch.object(window, "notify"):
                    self.assertFalse(window.close())
                worker.requestInterruption.assert_called_once()
                worker.finished.connect.assert_called_once_with(window.close)
                worker.isRunning.return_value = False
                self.assertTrue(window.close())


if __name__ == "__main__":
    unittest.main()
