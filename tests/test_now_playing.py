import json
import unittest
from unittest.mock import MagicMock, patch

from now_playing import current_song, find_lyrics


class NowPlayingTests(unittest.TestCase):
    def test_linux_falls_back_when_dbus_dependency_missing(self):
        song = ("Artist", "Title", 100000, 5000, True)
        with patch("now_playing.sys.platform", "linux"), \
                patch("now_playing._linux_song", side_effect=ImportError("dbus-next")), \
                patch("now_playing._linux_playerctl_song", return_value=song) as fallback:
            self.assertEqual(current_song(), song)
            fallback.assert_called_once()

    def test_playerctl_reads_a_playing_browser(self):
        from now_playing import _linux_playerctl_song

        def result(stdout, returncode=0):
            return type("Result", (), {"stdout": stdout, "returncode": returncode})()

        with patch("now_playing.subprocess.run", side_effect=[
            result("firefox.instance_1\n"), result("Playing\n"),
            result("George Lundy\x1fAlex G - Trash\x1f146000000\n"), result("39.5\n")]):
            self.assertEqual(_linux_playerctl_song(),
                             ("George Lundy", "Alex G - Trash", 146000, 39500, True))

    def test_browser_without_duration_is_still_detected(self):
        from now_playing import _linux_playerctl_song

        def result(stdout):
            return type("Result", (), {"stdout": stdout, "returncode": 0})()

        with patch("now_playing.subprocess.run", side_effect=[
            result("firefox.instance_1\n"), result("Playing\n"),
            result("lucas\x1f125 Rue Montmartre - Hit #2 (instrumental)\x1f\n"), result("13\n")]):
            self.assertEqual(_linux_playerctl_song(),
                             ("lucas", "125 Rue Montmartre - Hit #2 (instrumental)", 0, 13000, True))

    def test_exact_match_prefers_synced_lyrics_and_duration(self):
        results = [
            {"artistName": "Another artist", "trackName": "My song", "syncedLyrics": "wrong"},
            {"artistName": "The artist", "trackName": "My song", "duration": 240,
             "syncedLyrics": "[00:00.00]Wrong version"},
            {"artistName": "The artist", "trackName": "My song", "duration": 180,
             "syncedLyrics": "[00:00.00]Right version", "plainLyrics": "Right version"},
        ]
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(results).encode()
        with patch("now_playing.urlopen", return_value=response) as request:
            self.assertEqual(find_lyrics("The artist", "My song", 180_000), "[00:00.00]Right version")
        url = request.call_args.args[0].full_url
        self.assertIn("artist_name=The+artist", url)
        self.assertIn("track_name=My+song", url)

    def test_unmatched_song_does_not_display_other_songs_lyrics(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps([
            {"artistName": "Someone", "trackName": "Another", "plainLyrics": "Unrelated"},
        ]).encode()
        with patch("now_playing.urlopen", return_value=response):
            self.assertEqual(find_lyrics("The artist", "My song"), "")

    def test_browser_video_title_can_supply_artist_when_uploader_does_not_match(self):
        wrong = MagicMock()
        wrong.__enter__.return_value.read.return_value = b"[]"
        correct = MagicMock()
        correct.__enter__.return_value.read.return_value = json.dumps([
            {"artistName": "Alex G", "trackName": "Trash", "syncedLyrics": "[00:01.00]line"},
        ]).encode()
        with patch("now_playing.urlopen", side_effect=[wrong, correct]) as lookup:
            self.assertEqual(find_lyrics("George Lundy", "Alex G - Trash"), "[00:01.00]line")
        self.assertIn("artist_name=Alex+G", lookup.call_args.args[0].full_url)
