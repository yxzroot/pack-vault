import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QMimeData, Qt, QTimer, QUrl
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QFileDialog, QInputDialog, QMessageBox, QToolButton
import zipfile

import desktop
from desktop import AnimatedButton, NowPlayingWorker, PackVault, THEMES


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

                button = window.nav_buttons[1]
                QTest.mousePress(button, Qt.MouseButton.LeftButton)
                self.assertLess(button._ripple, 1.0)
                window.notify("Done!")
                self.assertIsNotNone(window._toast)
                window.close()

    def test_responsive_sidebar_and_keyboard_navigation(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            folder = base / "game/resourcepacks"
            folder.mkdir(parents=True)
            settings = base / "settings.json"
            settings.write_text(json.dumps({"tour_complete": True}))
            with patch("desktop.SETTINGS", settings), \
                    patch("desktop.discover_clients", return_value=[("Demo", folder)]):
                window = PackVault()
                window.show()
                window.resize(650, 560)
                self.app.processEvents()
                self.assertEqual(window.sidebar.width(), 64)
                self.assertEqual(window.nav_buttons[2].accessibleName(), "My library")
                self.assertEqual(window.nav_buttons[2].text(), "")
                window.nav_buttons[2].click()
                self.assertEqual(window.tabs.currentIndex(), 2)
                self.assertTrue(window.nav_buttons[2].isChecked())
                QTest.keyClick(window, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
                self.assertEqual(window.tabs.currentIndex(), 0)
                window.resize(1120, 760)
                self.app.processEvents()
                self.assertEqual(window.sidebar.width(), 222)
                self.assertEqual(window.nav_buttons[2].text(), "My library")
                window.close()

    def test_overview_is_dashboard_and_quick_access_opens_pack(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            folder = base / "game/resourcepacks"
            folder.mkdir(parents=True)
            library = base / "library"
            library.mkdir()
            with zipfile.ZipFile(folder / "Demo.zip", "w") as archive:
                archive.writestr("pack.mcmeta", '{"pack":{"pack_format":1,"description":"Demo"}}')
            settings = base / "settings.json"
            settings.write_text(json.dumps({"tour_complete": True, "client": str(folder)}))
            with patch("desktop.SETTINGS", settings), patch("desktop.DEFAULT_LIBRARY", library), \
                    patch("desktop.discover_clients", return_value=[("Demo client", folder)]):
                window = PackVault()
                window.show()
                self.app.processEvents()
                self.assertEqual(window.page_title.text(), "Dashboard")
                self.assertTrue(window.controls.isHidden())
                self.assertTrue(window.toolbar.isHidden())
                self.assertTrue(window.section.isHidden())
                self.assertEqual(window.dashboard_client_name.text(), "Demo client")
                self.assertEqual(window.stat_targets, [1, 1, 0])
                row = window.quick_packs.itemAt(0).widget()
                next(button for button in row.findChildren(AnimatedButton) if button.text() == "Open →").click()
                self.assertEqual(window.tabs.currentIndex(), 1)
                self.assertEqual(window.search.text(), "Demo.zip")
                self.assertFalse(window.controls.isHidden())
                self.assertFalse(window.toolbar.isHidden())
                window.tabs.setCurrentIndex(0)
                QTest.qWait(650)
                self.assertTrue(all(section.graphicsEffect() is None for section in window.dashboard_sections))
                window.close()

    def test_lyrics_player_shows_only_lyrics_and_tab_switches_finish(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            folder = base / "game/resourcepacks"
            folder.mkdir(parents=True)
            settings = base / "settings.json"
            settings.write_text(json.dumps({"tour_complete": True}))
            with patch("desktop.SETTINGS", settings), \
                    patch("desktop.discover_clients", return_value=[("Demo", folder)]):
                window = PackVault()
                window.show()
                window.lyrics_player.show_song(("Artist", "Private song title", 4000, 1500, True),
                                               "[00:01.00]First line\n[00:02.00]Second line")
                self.assertEqual(window.lyrics_player.current_lyric.text(), "First line")
                self.assertEqual(window.lyrics_player.next_lyric.text(), "Second line")
                self.assertNotIn("Private song title", window.lyrics_player.current_lyric.text())
                self.assertEqual(window.lyrics_player.findChildren(AnimatedButton), [])
                for index in (1, 3, 2, 0, 4, 0):
                    window.tabs.setCurrentIndex(index)
                QTest.qWait(750)
                self.assertIsNone(window._page_animation)
                self.assertIsNone(window.tabs.overlay)
                self.assertEqual(window.tabs.widget(0).pos().x(), 0)
                self.assertAlmostEqual(window.page_title.graphicsEffect().opacity(), 1.0)
                window.close()

    def test_now_playing_worker_looks_up_a_song_once(self):
        song = ("Artist", "Song", 120000, 1000, True)
        events = []
        with patch("desktop.current_song", return_value=song), \
                patch("desktop.find_lyrics", return_value="[00:00.00]A line") as lookup:
            worker = NowPlayingWorker()
            worker.updated.connect(lambda track, lyrics: events.append((track, lyrics)))
            worker.start()
            for _ in range(30):
                QTest.qWait(20)
                if len(events) >= 2:
                    break
            worker.requestInterruption()
            self.assertTrue(worker.wait(3000))
        self.assertEqual(events[:2], [(song, None), (song, "[00:00.00]A line")])
        lookup.assert_called_once_with("Artist", "Song", 120000)

    def test_pack_actions_remain_available_in_menus(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            folder = base / "game/resourcepacks"
            folder.mkdir(parents=True)
            library = base / "library"
            library.mkdir()
            with zipfile.ZipFile(folder / "Demo.zip", "w") as archive:
                archive.writestr("pack.mcmeta", '{"pack":{"pack_format":1,"description":"Demo"}}')
            settings = base / "settings.json"
            settings.write_text(json.dumps({"tour_complete": True, "client": str(folder)}))
            with patch("desktop.SETTINGS", settings), patch("desktop.DEFAULT_LIBRARY", library), \
                    patch("desktop.discover_clients", return_value=[("Demo", folder)]):
                window = PackVault()
                window.tabs.setCurrentIndex(1)
                window.version_box.setCurrentIndex(window.version_box.findData("1.20.4"))
                self.app.processEvents()
                menus = [button.menu() for i in range(window.cards[0].count())
                         for button in window.cards[0].itemAt(i).widget().findChildren(QToolButton)
                         if button.text().startswith("More")]
                self.assertEqual(len(menus), 1)
                actions = {action.text(): action for action in menus[0].actions()}
                self.assertTrue(any("checklist" in label for label in actions))
                self.assertTrue(any("Back up" in label for label in actions))
                self.assertTrue(any("Convert" in label for label in actions))
                with patch.object(window, "backup_pack") as backup:
                    next(action for label, action in actions.items() if "Back up" in label).trigger()
                    backup.assert_called_once_with("Demo.zip")
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

    def test_running_game_blocks_options_write(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Path(temp) / "settings.json"
            settings.write_text(json.dumps({"tour_complete": True}))
            with patch("desktop.SETTINGS", settings), patch("desktop.game_running", return_value=True):
                window = PackVault()
                with patch.object(window, "error") as error, patch("desktop.QMessageBox.question") as prompt:
                    self.assertFalse(window.confirm_options_write())
                    error.assert_called_once()
                    prompt.assert_not_called()
                window.close()

    def test_duplicate_scan_shows_results_without_modifying_packs(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            library = base / "library"
            library.mkdir()
            client = base / "client/resourcepacks"
            client.mkdir(parents=True)
            first = library / "First.zip"
            second = library / "Second.zip"
            first.write_bytes(b"same")
            second.write_bytes(b"same")
            settings = base / "settings.json"
            settings.write_text(json.dumps({"tour_complete": True}))
            with patch("desktop.SETTINGS", settings), patch("desktop.DEFAULT_LIBRARY", library), \
                    patch("desktop.discover_clients", return_value=[("Test client", client)]):
                window = PackVault()
                with patch.object(QMessageBox, "information") as dialog:
                    window.find_duplicates()
                    for _ in range(40):
                        QTest.qWait(20)
                        if window.duplicate_worker is None:
                            break
                    self.assertIsNone(window.duplicate_worker)
                    dialog.assert_called_once()
                self.assertEqual(first.read_bytes(), second.read_bytes())
                window.close()

    def test_profile_export_import_backup_restore_and_checklist(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            folder = base / "client/resourcepacks"
            folder.mkdir(parents=True)
            (folder / "A.zip").touch()
            options = folder.parent / "options.txt"
            options.write_text('resourcePacks:["A.zip"]\n')
            library = base / "library"
            library.mkdir()
            settings = base / "settings.json"
            settings.write_text(json.dumps({"tour_complete": True, "client": str(folder),
                "custom_clients": [{"name": "Test", "path": str(folder)}],
                "profiles": {str(folder): {"PvP": {"packs": ["A.zip"], "order": ["A.zip"]}}}}))
            exported = base / "loadout.json"
            with patch("desktop.SETTINGS", settings), patch("desktop.DEFAULT_LIBRARY", library):
                window = PackVault()
                with patch.object(QFileDialog, "getSaveFileName", return_value=(str(exported), "")):
                    window.export_saved_profile("PvP")
                self.assertTrue(exported.exists())
                window.settings["profiles"][str(folder)].pop("PvP")
                with patch.object(QFileDialog, "getOpenFileName", return_value=(str(exported), "")):
                    window.import_saved_profile()
                self.assertEqual(window.settings["profiles"][str(folder)]["PvP"]["order"], ["A.zip"])
                backup = desktop.write_order(folder, [])
                with patch.object(QInputDialog, "getItem", return_value=(
                        f"{backup.stem.removeprefix('options-')} · {backup.stat().st_size:,} bytes", True)), \
                        patch.object(window, "confirm_options_write", return_value=True), \
                        patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                    window.restore_options()
                self.assertIn('"A.zip"', options.read_text())
                window.version_box.setCurrentIndex(window.version_box.findData("1.20.4"))
                def complete_checklist():
                    dialog = QApplication.activeModalWidget()
                    for box in dialog.findChildren(QCheckBox):
                        box.setChecked(True)
                    dialog.accept()
                QTimer.singleShot(0, complete_checklist)
                window.show_test_checklist("A.zip")
                self.assertEqual(window.settings["tested_packs"][str((folder / "A.zip").resolve())]["version"],
                                 "1.20.4")
                window.close()


if __name__ == "__main__":
    unittest.main()
