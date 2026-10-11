#!/usr/bin/env python3
"""Resource-pack file operations shared by the desktop and optional web UI."""

import argparse
import json
import os
import platform
from pathlib import Path
import shutil
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import webbrowser
import zipfile


def app_directories(home=None, system=None, environ=None):
    """Return platform-native data and config directories (no third-party dependencies)."""
    home = Path(home) if home is not None else Path.home()
    system = system or platform.system()
    environ = os.environ if environ is None else environ
    if system == "Windows":
        data = Path(environ.get("LOCALAPPDATA") or home / "AppData/Local") / "PackVault"
        config = Path(environ.get("APPDATA") or home / "AppData/Roaming") / "PackVault"
    elif system == "Darwin":
        data = config = home / "Library/Application Support/PackVault"
    else:
        data = Path(environ.get("XDG_DATA_HOME") or home / ".local/share") / "pack-vault"
        config = Path(environ.get("XDG_CONFIG_HOME") or home / ".config") / "pack-vault"
    return data, config


def default_pack_folder(home=None, system=None, environ=None):
    home = Path(home) if home is not None else Path.home()
    system = system or platform.system()
    environ = os.environ if environ is None else environ
    if system == "Windows":
        return Path(environ.get("APPDATA") or home / "AppData/Roaming") / ".minecraft/resourcepacks"
    if system == "Darwin":
        return home / "Library/Application Support/minecraft/resourcepacks"
    oneclient = home / ".local/share/Polyfrost/OneClient/.minecraft/resourcepacks"
    return oneclient if oneclient.parent.is_dir() else home / ".minecraft/resourcepacks"


DEFAULT_PACKS = default_pack_folder()
DEFAULT_LIBRARY = app_directories()[0] / "packs"
MAX_UPLOAD = 128 * 1024 * 1024


def asset_path(name):
    """Find bundled assets in both source checkouts and PyInstaller builds."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / name


WEB = asset_path("index.html")


def pack_path(folder, name):
    if (not name or name in {".", ".."} or Path(name).name != name
            or any(char in name for char in '\\<>:"|?*')
            or name.endswith((" ", ".")) or any(ord(char) < 32 for char in name)):
        raise ValueError("Invalid pack name")
    path = folder / name
    return path


def is_pack(path):
    return path.is_dir() or (path.is_file() and path.name.lower().endswith((".zip", ".zip.disabled")))


def zip_member(archive, name):
    try:
        member = archive.getinfo(name)
    except KeyError:
        # Some ZIPs contain a single enclosing directory.
        matches = [n for n in archive.namelist() if n.endswith("/" + name) and n.count("/") == 1]
        if len(matches) != 1:
            return None
        member = archive.getinfo(matches[0])
    if member.file_size > 2 * 1024 * 1024:
        return None
    try:
        return archive.read(member)
    except (RuntimeError, NotImplementedError) as exc:
        raise ValueError("Pack ZIP is encrypted or uses an unsupported compression method") from exc


def pack_data(path):
    try:
        if path.is_dir():
            metadata = path / "pack.mcmeta"
            picture = path / "pack.png"
            meta = metadata.read_bytes() if metadata.is_file() and metadata.stat().st_size < 2 * 1024 * 1024 else None
            icon = picture.read_bytes() if picture.is_file() and picture.stat().st_size < 2 * 1024 * 1024 else None
        else:
            with zipfile.ZipFile(path) as archive:
                meta = zip_member(archive, "pack.mcmeta")
                icon = zip_member(archive, "pack.png")
        description = json.loads(meta)["pack"]["description"] if meta else "No pack.mcmeta found"
        if not isinstance(description, str):
            description = json.dumps(description, ensure_ascii=False)
        return description, icon if icon and len(icon) < 2 * 1024 * 1024 else None
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, UnicodeError):
        return "Could not read pack metadata", None


def list_packs(folder):
    if not folder.exists():
        return []
    packs = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        try:
            if (path.is_symlink() and not path.is_file()) or not is_pack(path):
                continue
            description, icon = pack_data(path)
            packs.append({"name": path.name, "description": description,
                          "enabled": not path.name.endswith(".disabled"),
                          "kind": "folder" if path.is_dir() else "zip",
                          "size": path.stat().st_size if path.is_file() else None,
                          "icon": icon is not None})
        except OSError:
            continue  # A pack may disappear while a launcher refreshes its directory.
    return packs


def toggle(folder, name):
    source = pack_path(folder, name)
    if not source.is_file() or not is_pack(source):
        raise ValueError("Only ZIP packs can be toggled")
    target_name = name[:-9] if name.endswith(".disabled") else name + ".disabled"
    target = pack_path(folder, target_name)
    if target.exists() or target.is_symlink():
        raise ValueError("A pack with that name already exists")
    source.rename(target)


def place_in_client(stored, target):
    """Link to the library; copy instead when Windows denies creating symlinks."""
    try:
        target.symlink_to(stored)
    except OSError as exc:
        if platform.system() != "Windows" or not (
                isinstance(exc, PermissionError) or getattr(exc, "winerror", None) == 1314):
            raise
        created = False
        try:
            with target.open("xb") as output, stored.open("rb") as original:
                created = True
                shutil.copyfileobj(original, output)
        except Exception:
            if created:
                target.unlink(missing_ok=True)
            raise


def import_pack(source, folder, library=DEFAULT_LIBRARY):
    """Copy a pack into our library and make it available to the selected client."""
    name = source.name
    link = pack_path(folder, name)
    stored = pack_path(library, name)
    if not name.lower().endswith(".zip"):
        raise ValueError("Choose a ZIP resource pack")
    hidden = pack_path(folder, name + ".disabled")
    if (link.exists() or link.is_symlink() or hidden.exists() or hidden.is_symlink()
            or stored.exists() or stored.is_symlink()):
        raise ValueError("A pack with this name is already in your library or this client")
    if source.stat().st_size > MAX_UPLOAD:
        raise ValueError("ZIP must be smaller than 128 MB")
    with zipfile.ZipFile(source) as archive:
        if zip_member(archive, "pack.mcmeta") is None:
            raise ValueError("ZIP has no pack.mcmeta")
    library.mkdir(parents=True, exist_ok=True)
    folder.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with stored.open("xb") as output, source.open("rb") as original:
            created = True
            shutil.copyfileobj(original, output)
        place_in_client(stored, link)
    except Exception:
        if created:
            stored.unlink(missing_ok=True)
        raise
    return stored


def install_from_library(name, folder, library=DEFAULT_LIBRARY):
    stored = pack_path(library, name)
    link = pack_path(folder, name)
    if not stored.is_file() or stored.is_symlink() or not name.lower().endswith(".zip"):
        raise ValueError("Select a ZIP from your library")
    hidden = pack_path(folder, name + ".disabled")
    if link.exists() or link.is_symlink() or hidden.exists() or hidden.is_symlink():
        raise ValueError("A pack with this name already exists in this client")
    folder.mkdir(parents=True, exist_ok=True)
    place_in_client(stored, link)


def discover_clients(home=None, system=None, environ=None):
    """Find known Minecraft directories without creating any of them."""
    home = Path(home) if home is not None else Path.home()
    system = system or platform.system()
    environ = os.environ if environ is None else environ
    candidates = []
    bases = []
    if system == "Windows":
        roaming = Path(environ.get("APPDATA") or home / "AppData/Roaming")
        local = Path(environ.get("LOCALAPPDATA") or home / "AppData/Local")
        candidates.append(("Minecraft (vanilla)", default_pack_folder(home, system, environ)))
        bases.extend(((roaming / "PrismLauncher/instances", "Prism"),
                      (local / "ModrinthApp/profiles", "Modrinth")))
        candidates.append(("OneClient", roaming / "Polyfrost/OneClient/.minecraft/resourcepacks"))
    elif system == "Darwin":
        support = home / "Library/Application Support"
        candidates.append(("Minecraft (vanilla)", default_pack_folder(home, system, environ)))
        bases.extend(((support / "PrismLauncher/instances", "Prism"),
                      (support / "ModrinthApp/profiles", "Modrinth")))
    else:
        candidates.append(("OneClient", home / ".local/share/Polyfrost/OneClient/.minecraft/resourcepacks"))
        candidates.append(("Minecraft (vanilla)", home / ".minecraft/resourcepacks"))
        bases.extend(((home / ".local/share/PrismLauncher/instances", "Prism"),
                      (home / ".var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher/instances", "Prism"),
                      (home / ".local/share/ModrinthApp/profiles", "Modrinth"),
                      (home / ".local/share/multimc/instances", "MultiMC")))
    candidates.extend([
        ("Lunar Client", home / ".lunarclient/offline/multiver/resourcepacks"),
        ("Lunar Client", home / ".lunarclient/resourcepacks"),
        ("Badlion Client", home / ".badlionclient/resourcepacks"),
        ("Feather Client", home / ".feather/resourcepacks"),
    ])
    for base, label in bases:
        if base.is_dir():
            for instance in base.iterdir():
                if instance.is_dir():
                    candidates.extend((f"{label} · {instance.name}", path) for path in
                                      (instance / ".minecraft/resourcepacks", instance / "resourcepacks"))
    found = []
    seen = set()
    for label, path in candidates:
        if (path.is_dir() or path.parent.is_dir()) and path not in seen:
            found.append((label, path))
            seen.add(path)
    return found


class Handler(BaseHTTPRequestHandler):
    folder = DEFAULT_PACKS
    library = DEFAULT_LIBRARY

    def send_data(self, data, content_type="application/json", status=200):
        if isinstance(data, (dict, list)):
            data = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/":
            self.send_data(WEB.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/packs":
            self.send_data({"folder": str(self.folder), "packs": list_packs(self.folder)})
        elif url.path == "/api/icon":
            try:
                name = parse_qs(url.query)["name"][0]
                path = pack_path(self.folder, name)
                if not is_pack(path):
                    raise ValueError("Pack not found")
                icon = pack_data(path)[1]
                if not icon or not icon.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("No PNG icon")
                self.send_data(icon, "image/png")
            except (KeyError, IndexError, ValueError, OSError):
                self.send_data({"error": "Icon not found"}, status=404)
        else:
            self.send_data({"error": "Not found"}, status=404)

    def do_POST(self):
        url = urlsplit(self.path)
        try:
            name = parse_qs(url.query)["name"][0]
            path = pack_path(self.folder, name)
            if url.path == "/api/import":
                stored = pack_path(self.library, name)
                hidden = pack_path(self.folder, name + ".disabled")
                if (not name.lower().endswith(".zip") or path.exists() or path.is_symlink()
                        or hidden.exists() or hidden.is_symlink() or stored.exists() or stored.is_symlink()):
                    raise ValueError("Use a new .zip filename")
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > MAX_UPLOAD:
                    raise ValueError("ZIP must be between 1 byte and 128 MB")
                # Create exclusively: never overwrite an existing pack.
                self.library.mkdir(parents=True, exist_ok=True)
                self.folder.mkdir(parents=True, exist_ok=True)
                created = False
                try:
                    with stored.open("xb") as output:
                        created = True
                        remaining = length
                        while remaining:
                            chunk = self.rfile.read(min(65536, remaining))
                            if not chunk:
                                raise ValueError("Incomplete upload")
                            output.write(chunk)
                            remaining -= len(chunk)
                    with zipfile.ZipFile(stored) as archive:
                        if zip_member(archive, "pack.mcmeta") is None:
                            raise ValueError("ZIP has no pack.mcmeta")
                    place_in_client(stored, path)
                except Exception:
                    if created:
                        stored.unlink(missing_ok=True)
                    raise
            elif url.path == "/api/toggle":
                toggle(self.folder, name)
            elif url.path == "/api/backup":
                if not path.exists() or (path.is_symlink() and not path.is_file()) or not is_pack(path):
                    raise ValueError("Pack not found")
                backups = self.folder.parent / "pack-vault-backups"
                backups.mkdir(exist_ok=True)
                destination = backups / path.name
                number = 1
                while destination.exists():
                    destination = backups / f"{path.name}.{number}"
                    number += 1
                if path.is_dir():
                    shutil.copytree(path, destination)
                else:
                    shutil.copy2(path, destination)
                self.send_data({"backup": str(destination)})
                return
            else:
                self.send_data({"error": "Not found"}, status=404)
                return
            self.send_data({"packs": list_packs(self.folder)})
        except (KeyError, IndexError, ValueError, OSError, zipfile.BadZipFile) as exc:
            self.send_data({"error": str(exc)}, status=400)


def main():
    parser = argparse.ArgumentParser(description="Local Minecraft resource pack manager")
    parser.add_argument("--folder", type=Path, default=DEFAULT_PACKS)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    Handler.folder = args.folder.expanduser().resolve()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    address = f"http://127.0.0.1:{server.server_port}"
    print(f"Pack Vault: {address}\nManaging: {Handler.folder}\nPress Ctrl+C to stop.")
    if not args.no_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
