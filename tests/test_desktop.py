import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

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


if __name__ == "__main__":
    unittest.main()
