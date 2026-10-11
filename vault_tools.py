"""Safe, opt-in utilities for sharing loadouts and finding duplicate ZIPs."""

from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import tempfile

import psutil

from app import pack_path


def game_running(folder):
    """Only flag a game whose --gameDir resolves to this client's game directory."""
    game = folder.parent.resolve()
    for process in psutil.process_iter(["name", "cmdline"]):
        try:
            info = process.info
            command = info.get("cmdline") or []
            executable = (info.get("name") or "").lower()
            if not ("java" in executable or "minecraft" in executable):
                continue
            for i, argument in enumerate(command):
                if argument == "--gameDir" and i + 1 < len(command):
                    location = command[i + 1]
                elif argument.startswith("--gameDir="):
                    location = argument.partition("=")[2]
                else:
                    continue
                if Path(location).expanduser().resolve() == game:
                    return True
        except (psutil.Error, OSError, ValueError, TypeError):
            continue  # Access denied is not proof the game is closed: still ask the user.
    return False


def _profile(name, entry):
    if not isinstance(name, str) or not name.strip() or len(name) > 48:
        raise ValueError("Profile name must be 1–48 characters")
    if isinstance(entry, list):  # Old availability-only profiles.
        entry = {"packs": entry, "order": None}
    if not isinstance(entry, dict):
        raise ValueError("Invalid profile")
    packs, order = entry.get("packs"), entry.get("order")
    if not isinstance(packs, list) or not all(isinstance(n, str) for n in packs):
        raise ValueError("Invalid profile pack list")
    if order is not None and (not isinstance(order, list) or
                              not all(isinstance(n, str) for n in order)):
        raise ValueError("Invalid profile order")
    for name in packs:
        pack_path(Path("."), name)
        if not name.lower().endswith(".zip"):
            raise ValueError("Profiles may only make ZIP packs available")
    for name in order or []:
        pack_path(Path("."), name)
    if len(packs) != len(set(packs)) or (order and len(order) != len(set(order))):
        raise ValueError("Profile contains duplicate pack names")
    return {"packs": packs, "order": order}


def export_profile(file, name, entry, minecraft_version=None):
    """Export configuration only, never pack files; do not overwrite another export."""
    data = {"format": "pack-vault-profile", "version": 1, "name": name,
            "minecraft_version": minecraft_version, **_profile(name, entry)}
    with file.open("x", encoding="utf-8") as output:
        json.dump(data, output, indent=2, ensure_ascii=False)
        output.write("\n")


def import_profile(file):
    if file.stat().st_size > 256 * 1024:
        raise ValueError("Profile exceeds 256 KB")
    data = json.loads(file.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("format") != "pack-vault-profile" or
            data.get("version") != 1):
        raise ValueError("Not a supported Pack Vault profile")
    name = data.get("name")
    return name, _profile(name, data)


def duplicate_zips(folders, cancelled=lambda: False):
    """Hash likely duplicates on demand; never alter packs or follow duplicate symlinks."""
    by_size = defaultdict(list)
    seen = set()
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if not path.name.lower().endswith((".zip", ".zip.disabled")) or not path.is_file():
                continue
            try:
                real = path.resolve()
                if real in seen:
                    continue
                seen.add(real)
                by_size[path.stat().st_size].append(path)
            except OSError:
                continue
    duplicates = []
    for paths in by_size.values():
        if cancelled():
            return []
        if len(paths) < 2:
            continue
        by_hash = defaultdict(list)
        for path in paths:
            if cancelled():
                return []
            digest = sha256()
            try:
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        if cancelled():
                            return []
                        digest.update(chunk)
                by_hash[digest.hexdigest()].append(path)
            except OSError:
                continue
        duplicates.extend(group for group in by_hash.values() if len(group) > 1)
    return sorted(duplicates, key=lambda group: str(group[0]))


def pack_backups(folder):
    directory = folder.parent / "pack-vault-backups"
    if directory.is_symlink() or not directory.is_dir():
        return []
    return sorted((path for path in directory.iterdir() if not path.is_symlink() and
                   (path.is_file() and re.search(r"\.zip(?:\.disabled)?(?:\.\d+)?$", path.name, re.I)
                    or path.is_dir() and (path / "pack.mcmeta").is_file())),
                  key=lambda path: path.name.lower())


def restore_pack_backup(folder, backup):
    """Restore a pack as a new filename. Never replace another client pack."""
    backup = Path(backup)
    if backup.is_symlink() or backup not in pack_backups(folder):
        raise ValueError("Choose a Pack Vault pack backup from this client")
    name = re.sub(r"\.\d+$", "", backup.name)
    pack_path(folder, name)
    if backup.is_file() and not name.lower().endswith((".zip", ".zip.disabled")):
        raise ValueError("Backup is not a ZIP pack")
    stem = name.removesuffix(".zip.disabled").removesuffix(".zip")
    ext = name[len(stem):]
    folder.mkdir(parents=True, exist_ok=True)
    for count in range(1, 1001):
        target = pack_path(folder, f"{stem}-restored-{count}{ext}")
        hidden = folder / (target.name + ".disabled")
        if not target.exists() and not target.is_symlink() and not hidden.exists() and not hidden.is_symlink():
            break
    else:
        raise ValueError("Too many restored copies; choose a different folder")
    if backup.is_file():
        created = False
        try:
            with target.open("xb") as output, backup.open("rb") as original:
                created = True
                shutil.copyfileobj(original, output, length=1024 * 1024)
        except Exception:
            if created:
                target.unlink(missing_ok=True)
            raise
    else:
        # Stage complete directories before moving into the client folder.
        with tempfile.TemporaryDirectory(dir=folder, prefix=".pack-vault-restore-") as staging:
            copy = Path(staging) / "pack"
            shutil.copytree(backup, copy, symlinks=True)
            if target.exists() or target.is_symlink():
                raise ValueError("Restore target appeared while copying")
            copy.rename(target)
    return target
