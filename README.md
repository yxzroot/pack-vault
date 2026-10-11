# Pack Vault

A desktop resource-pack manager for **Minecraft Java Edition**. Keep one pack library, use it across clients, preview textures, and switch between loadouts. Available for Linux, Windows, and macOS. No account required; update checks are opt-in.

## Download

Get the build for your system from the [latest release](https://github.com/yxzroot/pack-vault/releases/latest), then extract the archive before opening the app. Development builds are also available under **Artifacts** in the [build workflow](https://github.com/yxzroot/pack-vault/actions/workflows/build.yml).

| Platform | Download | Start the app | Library location |
| --- | --- | --- | --- |
| Windows | `PackVault-Windows.zip` | `PackVault/PackVault.exe` | `%LOCALAPPDATA%\PackVault\packs` |
| macOS | `PackVault-macOS.zip` | `PackVault.app` | `~/Library/Application Support/PackVault/packs` |
| Linux | `PackVault-Linux.tar.gz` | `PackVault/PackVault` | `$XDG_DATA_HOME/pack-vault/packs` (defaults to `~/.local/share/pack-vault/packs`) |

Builds are **unsigned**. Windows SmartScreen and macOS Gatekeeper may show a warning; on macOS, right-click the app and choose **Open**.

## Getting started

1. Open **This client** and choose a detected Minecraft installation. If yours isn't listed, use **Add folder** to select its `resourcepacks` directory.
2. Click **Import ZIP** or drop ZIP files into the window. Pack Vault keeps a copy in **My library** and makes the pack available in that client. Existing packs are never overwritten or moved.
3. To use the pack elsewhere, switch clients and choose **My library → Install**. The client list refreshes while the app is open.

Pack Vault looks for vanilla Minecraft, OneClient, Lunar, Badlion, Feather, Prism, Modrinth, and MultiMC. Some launcher installations may need **Add folder**. You can browse and search packs, preview sample textures, hide or show ZIPs, and back up client packs. The sidebar offers five themes: Midnight, Sakura, Forest, Daylight, and Apple. On Linux and macOS, installed packs are linked to the library ZIP; on Windows, Pack Vault falls back to a separate copy when symlinks require elevated privileges. Replacing a library file will **not** update an independent Windows copy.

## More you can do

### Versions and conversion

Choose your Java Edition version on **This client**. Pack Vault knows released resource-pack formats from **1.6.1 through 26.3** and can detect the version from some OneClient, Prism, Modrinth, and vanilla launcher metadata. Select it manually if detection is uncertain. Pack cards show declared compatibility; snapshots, Bedrock, and unknown versions aren't guessed.

**Convert** creates a *new* ZIP for the selected version. It updates `pack.mcmeta` and adds legacy block/item texture-path aliases when crossing the 1.13 boundary. The conversion report lists added aliases, skipped collisions, removed overlays, and models, shaders, and sounds copied without conversion. **This cannot guarantee the pack works in-game.** The original ZIP stays untouched; use a pack card's **In-game checklist** to record your own test results.

### Pack order, profiles, and recovery

**Close Minecraft before changing selection or pack order.** Pack Vault tries to detect a running game, but some launchers don't expose enough information for a reliable warning. If the game is open, it may overwrite your changes.

- In **Pack order**, tick packs, drag them into priority order (top = highest), then save. Pack Vault backs up `options.txt` before writing it and preserves built-in pack entries. Start the client once first if it doesn't have `options.txt` yet.
- **Restore backup…** restores a full `options.txt` snapshot, saving the current file first. **Restore pack…** copies a saved pack under a new name without replacing another pack. If a selected ZIP is missing, Pack Vault asks you to restore it or change the selection in Minecraft rather than silently dropping it.
- **Profiles** save the available ZIPs and selected order. Activating a profile hides other ZIPs with `.zip.disabled` (without deleting them), and can install missing ZIPs from your library. Deactivating restores the previous selection; folder packs aren't hidden. Older availability-only profiles still work.
- **Export** and **Import profile…** share a JSON loadout without overwriting an existing profile. The export **does not contain ZIP files**; install those separately.

Backups are stored in `pack-vault-backups` beside that client's `resourcepacks` directory.

### Scans and updates

- **Scan overlaps** shows asset paths shared by available ZIPs. Overlap isn't necessarily a problem: Minecraft resolves it using pack priority.
- **Find duplicates** compares client and library ZIPs by SHA-256 when you ask it to. It ignores symlinks to the same file and **never deletes packs**.
- **Track updates** on a library ZIP accepts a Modrinth pack URL or slug. Pack Vault tries to match its SHA-512 to a Modrinth release; otherwise, the latest release becomes the starting point. **Check updates** contacts Modrinth only when clicked (up to 10 tracked packs). Compatible downloads are hash-verified and saved as *new* library packs. Installation and selection changes need separate confirmation, and **Restore previous** can switch selection back to the earlier ZIP. Nothing checks or downloads automatically.

### Dashboard lyrics

The dashboard shows **lyrics only**, not song titles, artwork, or playback controls. It follows music playing in another app when the operating system exposes it: Linux MPRIS (via `dbus-next` or `playerctl`), Windows media sessions, and Spotify or Music on macOS (which may request Automation permission). Browser and other players that don't publish playback information may not be detected.

For lyric lookup, Pack Vault sends the detected **artist and title** to [LRCLIB](https://lrclib.net/) when the track changes. If a browser reports a video title like `Artist - Song`, it may try those fields as a second lookup. **No audio is uploaded.** Timed lyrics follow playback position when available; otherwise, a plain lyric sheet is shown. If no lyrics are found, the dashboard says so.

## Run from source

Install Python 3.12 or newer, then run:

```bash
python -m pip install -r requirements.txt
python desktop.py
```

On Linux, `./launch.sh` also starts the desktop app (install dependencies first). The older local web prototype can be run with `python app.py`; the desktop app is the maintained version. Client choices, themes, and tour state are saved in `%APPDATA%\PackVault` on Windows, `~/Library/Application Support/PackVault` on macOS, or `${XDG_CONFIG_HOME:-~/.config}/pack-vault` on Linux.

## Build and test

```bash
python -m unittest discover -s tests -v
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean pack-vault.spec
```

For headless Linux tests, set `QT_QPA_PLATFORM=offscreen`. CI tests and builds Linux, Windows, and macOS apps. Pushing a `v*` tag also publishes those builds to a GitHub Release; Windows and macOS builds are not code-signed or notarized.

**Shoutout:** I built Pack Vault with help from GPT-6 Sol (OpenAI) in OpenCode.
