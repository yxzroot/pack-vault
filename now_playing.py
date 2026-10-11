"""Best-effort system media detection and on-demand LRCLIB lyrics lookup."""

import asyncio
import json
import subprocess
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def current_song():
    """Return (artist, title, duration_ms, position_ms, playing) or None."""
    if sys.platform.startswith("linux"):
        try:
            return asyncio.run(asyncio.wait_for(_linux_song(), timeout=2))
        except Exception:
            # Source checkouts may run with system Python without dbus-next.
            # playerctl speaks the same MPRIS protocol when it is installed.
            return _linux_playerctl_song()
    try:
        if sys.platform == "win32":
            return asyncio.run(asyncio.wait_for(_windows_song(), timeout=2))
        if sys.platform == "darwin":
            return _mac_song()
    except Exception:  # OS media APIs and player implementations fail in different ways.
        return None
    return None


def _linux_playerctl_song():
    try:
        players = subprocess.run(["playerctl", "-l"], capture_output=True, text=True,
                                 timeout=2, check=False).stdout.splitlines()
        for player in players:
            if not player:
                continue
            command = ["playerctl", "-p", player]
            status = subprocess.run(command + ["status"], capture_output=True,
                                    text=True, timeout=2, check=False)
            if status.returncode or status.stdout.strip() != "Playing":
                continue
            metadata = subprocess.run(command + ["metadata", "--format",
                                                  "{{artist}}\x1f{{title}}\x1f{{mpris:length}}"],
                                      capture_output=True, text=True, timeout=2, check=False)
            fields = metadata.stdout.rstrip("\r\n").split("\x1f")
            if metadata.returncode or len(fields) != 3 or not fields[0].strip() or not fields[1].strip():
                continue
            position = subprocess.run(command + ["position"], capture_output=True,
                                      text=True, timeout=2, check=False)
            return fields[0].strip(), fields[1].strip(), int(fields[2] or 0) // 1000, \
                int(float(position.stdout.strip() or 0) * 1000), True
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


async def _linux_song():
    from dbus_next.aio import MessageBus
    from dbus_next import Message, MessageType

    bus = await MessageBus().connect()
    try:
        reply = await bus.call(Message(destination="org.freedesktop.DBus",
                                       path="/org/freedesktop/DBus", interface="org.freedesktop.DBus",
                                       member="ListNames"))
        if reply.message_type != MessageType.METHOD_RETURN:
            return None
        for name in sorted(n for n in reply.body[0] if n.startswith("org.mpris.MediaPlayer2.")):
            reply = await bus.call(Message(destination=name, path="/org/mpris/MediaPlayer2",
                                           interface="org.freedesktop.DBus.Properties", member="GetAll",
                                           signature="s", body=["org.mpris.MediaPlayer2.Player"]))
            if reply.message_type != MessageType.METHOD_RETURN:
                continue
            props = {key: value.value for key, value in reply.body[0].items()}
            if props.get("PlaybackStatus") != "Playing":
                continue
            meta = {key: value.value for key, value in props.get("Metadata", {}).items()}
            artist = meta.get("xesam:artist", [])
            title = meta.get("xesam:title", "")
            if artist and title:
                return str(artist[0]), str(title), int(meta.get("mpris:length", 0) // 1000), \
                    int(props.get("Position", 0) // 1000), True
    finally:
        bus.disconnect()
    return None


async def _windows_song():
    from winrt.windows.media.control import (GlobalSystemMediaTransportControlsSessionManager as Manager,
                                             GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status)

    manager = await Manager.request_async()
    sessions = manager.get_sessions()
    preferred = manager.get_current_session()
    for session in ([preferred] if preferred else []) + [s for s in sessions if s != preferred]:
        if session.get_playback_info().playback_status != Status.PLAYING:
            continue
        props = await session.try_get_media_properties_async()
        if props.artist and props.title:
            timeline = session.get_timeline_properties()
            return props.artist, props.title, int(timeline.end_time.total_seconds() * 1000), \
                int(timeline.position.total_seconds() * 1000), True
    return None


def _mac_song():
    # AppleScript reports metadata from native Music and Spotify only; macOS may ask
    # for Automation permission. Do not start either app just to check playback.
    for app in ("Spotify", "Music"):
        script = (f'if application "{app}" is running then\n'
                  f'  tell application "{app}"\n'
                  '    if player state is playing then\n'
                  '      return (artist of current track) & linefeed & '
                  '(name of current track) & linefeed & '
                  '(duration of current track) & linefeed & player position\n'
                  '    end if\n  end tell\nend if')
        result = subprocess.run(["osascript", "-e", script], capture_output=True,
                                text=True, timeout=2, check=False)
        fields = result.stdout.strip().splitlines()
        if result.returncode == 0 and len(fields) == 4 and fields[0] and fields[1]:
            duration = float(fields[2])
            # Music reports duration in seconds; Spotify reports milliseconds.
            return fields[0], fields[1], int(duration if app == "Spotify" else duration * 1000), \
                int(float(fields[3]) * 1000), True
    return None


def find_lyrics(artist, title, duration_ms=0):
    """Try media metadata, then a browser-style 'Artist - Song' video title."""
    alternative = [part.strip() for part in title.split(" - ", 1)] if " - " in title else []
    try:
        lyrics = _search_lyrics(artist, title, duration_ms)
    except OSError:
        if len(alternative) != 2 or not all(alternative):
            raise
        lyrics = ""
    if lyrics or len(alternative) != 2 or not all(alternative):
        return lyrics
    return _search_lyrics(alternative[0], alternative[1], duration_ms)


def _search_lyrics(artist, title, duration_ms):
    query = urlencode({"artist_name": artist, "track_name": title})
    request = Request("https://lrclib.net/api/search?" + query,
                      headers={"User-Agent": "PackVault/1.0 (lyrics dashboard)"})
    with urlopen(request, timeout=5) as response:
        results = json.loads(response.read(512_001))
    if not isinstance(results, list):
        return ""
    matches = [entry for entry in results if isinstance(entry, dict)
               and str(entry.get("trackName", "")).casefold() == title.casefold()
               and str(entry.get("artistName", "")).casefold() == artist.casefold()
               and not entry.get("instrumental")]
    if duration_ms:
        close = [entry for entry in matches if isinstance(entry.get("duration"), (int, float))
                 and abs(entry["duration"] * 1000 - duration_ms) < 12_000]
        if close:
            matches = close
    for entry in matches:
        lyrics = entry.get("syncedLyrics") or entry.get("plainLyrics")
        if isinstance(lyrics, str):
            return lyrics[:32_000]
    return ""
