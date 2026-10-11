"""Local lyric-sheet parsing; no network lookup or copyrighted lyric database."""

import re


TIMESTAMP = re.compile(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]")


def parse_lyrics(text):
    """Return (timestamp_ms, line) pairs from LRC, or a static lyric sheet."""
    entries = []
    for line in text.splitlines():
        stamps = list(TIMESTAMP.finditer(line))
        lyric = TIMESTAMP.sub("", line).strip()
        if not stamps or not lyric:
            continue
        for stamp in stamps:
            fraction = (stamp[3] or "").ljust(3, "0")
            milliseconds = (int(stamp[1]) * 60 + int(stamp[2])) * 1000 + int(fraction or 0)
            entries.append((milliseconds, lyric))
    if entries:
        return sorted(entries), ""
    # Ignore metadata tags in an LRC without timed lines.
    plain = "\n".join(line for line in text.splitlines()
                      if line.strip() and not re.match(r"^\[[a-zA-Z]+:", line.strip()))
    return [], plain.strip()
