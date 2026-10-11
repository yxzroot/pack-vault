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

Choose a detected client (or **Add folder** for any other `resourcepacks` directory), then click **Import ZIP** or drag ZIP files into the window. Pack Vault saves a copy in your library and makes it available to the selected client. Use **My library → Install** to add it to another client. It refreshes the discovered client list when running. Existing packs are never overwritten or moved.

On Linux and macOS, the client gets a symlink to your library's ZIP. On Windows, Pack Vault tries the same but automatically copies the ZIP if symlink creation requires elevated privileges. A Windows copy is independent: replacing a file in the library does not update that client's copy. You can hide/show ZIPs, back up packs (next to the client's `resourcepacks` directory), browse/search packs, and pick a random one.

**Minecraft version & conversion:** Select your Java Edition version at the top. This is **not limited to 1.8.9**: listed releases run from 1.6.1 through 26.3, and OneClient, Prism, Modrinth and some vanilla launcher profiles are detected automatically. Pick your version manually if detection is ambiguous. Pack cards check declared format ranges as well as individual formats. **Convert** makes a new copy for the selected version; it updates `pack.mcmeta` (including modern major/minor formats) and adds legacy block/item texture path aliases when crossing the 1.13 boundary. This is **best effort**, not a guarantee that models, shaders, sounds, overlays, or all textures will work across versions. Overlays are removed when converting between different formats, and the original ZIP is never modified. Test converted packs in Minecraft. Bedrock, snapshots and unrecognized releases are not assigned guessed formats.

**Pack order & profiles:** Close Minecraft before using the Pack order tab or activating a profile; Minecraft may overwrite changes while running. Drag and tick packs in Pack order (top = highest priority), then save. Pack Vault backs up `options.txt` into `pack-vault-backups` next to `resourcepacks` before changing Minecraft's selected pack list; built-in pack entries are preserved. If an existing selected ZIP is missing, it asks you to restore it or change the selection in Minecraft instead of silently discarding it. A profile saves both the available ZIPs and the selected pack order; activating hides other ZIPs with `.zip.disabled` (never deletes them), selects the saved packs in `options.txt`, and can install missing ZIPs from your library. Deactivating restores the previous availability and selection. Folder packs are not hidden. Older saved profiles still work as availability-only profiles. If a client has no `options.txt`, start it once first; order editing is unavailable until then. Pack cards also offer sample texture previews.

**Overlap scan:** Click **Scan overlaps** to see asset paths shared by multiple available ZIPs. Overlap is not necessarily an error: Minecraft resolves it according to its own pack order.

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
