# Pack Vault

A colorful, animated desktop app for managing Minecraft resource packs across clients. Keep one library, install packs into multiple clients, and preview icons/descriptions. No account required; online update checks are opt-in.

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

On Linux and macOS, the client gets a symlink to your library's ZIP. On Windows, Pack Vault tries the same but automatically copies the ZIP if symlink creation requires elevated privileges. A Windows copy is independent: replacing a file in the library does not update that client's copy. You can hide/show ZIPs, back up packs (next to the client's `resourcepacks` directory), browse/search packs, and pick a random one. Minecraft's saved pack selection isn't changed.

**Profiles:** In the Profiles tab, save the available ZIPs in the selected client and activate a loadout in one click. Other ZIPs are hidden by renaming to `.zip.disabled` (not deleted); deactivating restores the available ZIPs from before activation. Folder packs and Minecraft's saved pack selection are not changed. If a profile needs a ZIP from your library, it is installed into the selected client.

**Overlap scan:** Click **Scan overlaps** to see asset paths shared by multiple available ZIPs. Overlap is not necessarily an error: Minecraft resolves it according to its own pack order.

**Update checks:** In **My library**, choose **Track updates** on a ZIP and enter its Modrinth resource-pack URL or slug. This stores the current latest release as a baseline (it does **not** verify the version inside your ZIP); **Check updates** contacts `api.modrinth.com` only when clicked and reports releases published after that baseline. Up to 10 tracked packs are checked per click. It never downloads, replaces, or updates packs automatically. Packs without a known Modrinth project cannot be checked automatically.

The app checks common locations for vanilla Minecraft, OneClient, Lunar, Badlion, Feather, Prism, Modrinth, and MultiMC; some launcher versions may require **Add folder**. Client choices, themes (Midnight, Sakura, Forest, Daylight, Apple), and the first-run tour state are saved to the platform's config directory (`%APPDATA%\\PackVault`, `~/Library/Application Support/PackVault`, or `${XDG_CONFIG_HOME:-~/.config}/pack-vault`).

## Build / test

```bash
python -m unittest discover -s tests -v
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean pack-vault.spec
```

For Linux without a graphical session, run tests with `QT_QPA_PLATFORM=offscreen`. CI runs tests and builds native artifacts on Windows, macOS, and Linux. macOS/Windows builds are not code-signed or notarized.

Pushing a version tag such as `v1.0.0` runs all platform tests, bundles each build and uploads the three ZIPs to the matching GitHub Release.
