import unittest

from lyrics import parse_lyrics


class LyricsTests(unittest.TestCase):
    def test_lrc_multiple_stamps_sorted_and_fractional_seconds(self):
        lines, plain = parse_lyrics("[ar:Artist]\n[00:02.5][00:01.20]Hello\n[01:03.123]World")
        self.assertEqual(lines, [(1200, "Hello"), (2500, "Hello"), (63123, "World")])
        self.assertEqual(plain, "")

    def test_plain_sheet_and_metadata(self):
        self.assertEqual(parse_lyrics("[ar:Someone]\nFirst line\nSecond line"),
                         ([], "First line\nSecond line"))
