import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import zipfile

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
                self.assertEqual(window.tabs.count(), 4)
                self.assertIn("Apple", THEMES)
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
            library = base / "library"
            library.mkdir()
            for path in (folder / "A.zip", library / "B.zip", base / "C.zip"):
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("pack.mcmeta", '{"pack":{"description":"test"}}')
            settings = base / "settings.json"
            settings.write_text(json.dumps({"tour_complete": True, "client": str(folder),
                "custom_clients": [{"name": "Test", "path": str(folder)}],
                "profiles": {str(folder): {"B only": ["B.zip"]}}}))
            with patch("desktop.SETTINGS", settings), patch("desktop.DEFAULT_LIBRARY", library):
                window = PackVault()
                window.show()
                window.tabs.setCurrentIndex(3)
                window.activate_profile("B only")
                self.assertTrue((folder / "A.zip.disabled").exists())
                self.assertTrue((folder / "B.zip").exists())
                self.assertEqual(json.loads(settings.read_text())["profile_previous"][str(folder)], ["A.zip"])
                window.deactivate_profile()
                self.assertTrue((folder / "A.zip").exists())
                self.assertTrue((folder / "B.zip.disabled").exists())

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
                lookup.assert_called_once_with("cool")
                window.close()


if __name__ == "__main__":
    unittest.main()
