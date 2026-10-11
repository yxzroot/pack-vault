# Pack Vault

A colorful, animated desktop app for managing Minecraft resource packs across clients. Keep one library, install packs into multiple clients, and preview icons/descriptions. No account required; online update checks are opt-in.

**Little shoutout:** Built with yxzroot and GPT-6 Sol (OpenAI) in OpenCode — from a tiny pack manager to a cross-platform app with animations and releases.

## Download and run

Download the ZIP for your system from the [latest release](https://github.com/yxzroot/pack-vault/releases/latest) and extract it first. Development builds also appear under **Artifacts** in the [build workflow](https://github.com/yxzroot/pack-vault/actions/workflows/build.yml).

| Platform | Start the app | Where the app stores your library |
| --- | --- | --- |
| Windows | Run `PackVault/PackVault.exe` | `%LOCALAPPDATA%\\PackVault\\packs` |
| macOS | Open `PackVault.app` | `~/Library/Application Support/PackVault/packs` |
| Linux | Run `PackVault/PackVault` | `${XDG_DATA_HOME:-~/.local/share}/pack-vault/packs` |

These builds are **unsigned**. Windows SmartScreen and macOS Gatekeeper may ask you to confirm opening an app downloaded from the internet. For macOS, right-click the app and choose **Open**. You can also run from source instead of using a downloaded build.

## Run from source

Install Python 3.12 or newer, then in this repository:

```bash
python -m pip install -r requirements.txt
python desktop.py
```

On Linux you can also run `./launch.sh`. A local web prototype remains available with `python app.py`; the desktop app is the maintained experience.

## How it works

Open **This client**, choose a detected client (or **Add folder** for any other `resourcepacks` directory), then click **Import ZIP** or drag ZIP files into the window. Pack Vault saves a copy in your library and makes it available to the selected client. Use **My library → Install** to add it to another client. It refreshes the discovered client list when running. Existing packs are never overwritten or moved.

**Dashboard lyrics:** Pack Vault follows music playing in other apps and shows lyric lines only—no player controls, artwork, or track metadata. It looks up the detected artist and title through [LRCLIB](https://lrclib.net/) when the song changes; **those two fields leave your device**. Browser video titles formatted `Artist - Song` may trigger a second lookup using that artist and title if the uploader's metadata doesn't match. No audio is uploaded, and if a song is not found the panel says so. Detection is best-effort: Linux requires an MPRIS-compatible player and a session D-Bus (with `dbus-next` or the `playerctl` fallback), Windows requires a player that publishes a Windows media session, and macOS supports Spotify and Music (Automation permission may be requested). Browser players and apps that don't share playback data might not be detected. Timed lyrics follow playback position when the player exposes it; other lyrics appear as a plain sheet.

On Linux and macOS, the client gets a symlink to your library's ZIP. On Windows, Pack Vault tries the same but automatically copies the ZIP if symlink creation requires elevated privileges. A Windows copy is independent: replacing a file in the library does not update that client's copy. You can hide/show ZIPs, back up packs (next to the client's `resourcepacks` directory), browse/search packs, and pick a random one.

**Minecraft version & conversion:** Select your Java Edition version at the top. This is **not limited to 1.8.9**: listed releases run from 1.6.1 through 26.3, and OneClient, Prism, Modrinth and some vanilla launcher profiles are detected automatically. Pick your version manually if detection is ambiguous. Pack cards check declared format ranges as well as individual formats. **Convert** makes a new copy for the selected version; it updates `pack.mcmeta` (including modern major/minor formats) and adds legacy block/item texture path aliases when crossing the 1.13 boundary. A conversion report counts added aliases, skipped collisions, removed overlays and model/shader/sound files copied without conversion. This is **best effort**, not a guarantee that models, shaders, sounds, overlays, or all textures will work across versions. Overlays are removed when converting between different formats, and the original ZIP is never modified. Use the **In-game checklist** on a pack card to record *your own* verification for a selected version. Bedrock, snapshots and unrecognized releases are not assigned guessed formats.

**Pack order & profiles:** Close Minecraft before using the Pack order tab or activating a profile; Minecraft may overwrite changes while running. Pack Vault blocks changes if it detects a running Java process with this client's game directory, but some launchers don't expose that path, so **still close the game yourself**. Drag and tick packs in Pack order (top = highest priority), then save. Pack Vault backs up `options.txt` into `pack-vault-backups` next to `resourcepacks` before changing Minecraft's selected pack list; built-in pack entries are preserved. **Restore backup…** restores a snapshot of the *whole* `options.txt` and backs up the current file first, even if it has become unreadable. **Restore pack…** copies a saved ZIP or folder pack into the client with a new name and never overwrites an existing pack. If an existing selected ZIP is missing, Pack Vault asks you to restore it or change selection in Minecraft rather than silently discarding it. A profile saves both available ZIPs and selected pack order; activating hides other ZIPs with `.zip.disabled` (never deletes them), selects the saved packs in `options.txt`, and can install missing ZIPs from your library. Deactivating restores previous availability and selection. **Export** and **Import profile…** share a JSON loadout without overwriting an existing profile; ZIP files themselves are *not* included, so install those separately. Folder packs are not hidden. Older saved profiles still work as availability-only profiles. If a client has no `options.txt`, start it once first; order editing is unavailable until then. Pack cards also offer sample texture previews.

**Overlap scan:** Click **Scan overlaps** to see asset paths shared by multiple available ZIPs. Overlap is not necessarily an error: Minecraft resolves it according to its own pack order.

**Duplicates:** Click **Find duplicates** for an on-demand SHA-256 scan of client and library ZIPs. The report ignores symlinks to the same library file, includes independent copies, and never deletes anything.

**Update checks:** In **My library**, choose **Track updates** on a ZIP and enter its Modrinth resource-pack URL or slug. Pack Vault tries to match its SHA-512 to a release returned by Modrinth; if no match is found, the latest release becomes the tracking baseline instead. **Check updates** contacts `api.modrinth.com` only when clicked. If a release explicitly lists the selected Minecraft version, you can choose to download it; the SHA-512 is verified before the ZIP is saved as a **new** library pack. Installation and changing the selected pack require separate confirmations; the previous ZIP remains available, with **Restore previous** on the updated library card for one-click selection rollback. Up to 10 tracked packs are checked per click. Nothing is checked or downloaded automatically. Packs without a known Modrinth project cannot be checked automatically.

The app checks common locations for vanilla Minecraft, OneClient, Lunar, Badlion, Feather, Prism, Modrinth, and MultiMC; some launcher versions may require **Add folder**. Client choices, themes (Midnight, Sakura, Forest, Daylight, Apple), and the first-run tour state are saved to the platform's config directory (`%APPDATA%\\PackVault`, `~/Library/Application Support/PackVault`, or `${XDG_CONFIG_HOME:-~/.config}/pack-vault`).

## Build / test

```bash
python -m unittest discover -s tests -v
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean pack-vault.spec
```

For Linux without a graphical session, run tests with `QT_QPA_PLATFORM=offscreen`. CI runs tests and builds native artifacts on Windows, macOS, and Linux. macOS/Windows builds are not code-signed or notarized.

Pushing a version tag such as `v1.0.0` runs all platform tests, bundles each build and uploads the three ZIPs to the matching GitHub Release.
