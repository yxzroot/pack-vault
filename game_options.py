"""Read and safely update Minecraft's selected resource-pack order in options.txt."""

from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from app import pack_path


def _available(folder, name):
    try:
        path = pack_path(folder, name)
        return path.is_file() or path.is_dir()
    except ValueError:
        return False


def _options(folder):
    file = folder.parent / "options.txt"
    if file.is_symlink():
        raise ValueError("options.txt is a symlink; Pack Vault won't replace launcher-managed settings.")
    if not file.is_file():
        raise ValueError("This client has no options.txt yet. Start Minecraft once, then close it.")
    original = file.read_bytes()
    text = original.decode("utf-8")
    lines = text.splitlines(keepends=True)
    matches = [line.partition(":")[2].strip() for line in lines if line.startswith("resourcePacks:")]
    if len(matches) != 1:
        raise ValueError("Could not safely read resourcePacks in options.txt")
    values = json.loads(matches[0])
    if not isinstance(values, list) or not all(isinstance(entry, str) for entry in values):
        raise ValueError("Unsupported resourcePacks value in options.txt")
    return file, original, lines, values


def read_order(folder):
    """Minecraft stores priority last. Return names in the same low-to-high order."""
    values = _options(folder)[3]
    # A selected pack absent from the folder is often temporarily unavailable.
    # Do not silently drop it when the user saves an order or profile.
    names = [entry.removeprefix("file/") for entry in values if entry != "vanilla"
             and (entry.startswith("file/") or entry.lower().endswith(".zip")
                  or _available(folder, entry))]
    missing = [name for name in names if not _available(folder, name)]
    if missing:
        raise ValueError(f"Selected pack is unavailable: {missing[0]}. Restore it or change selection in Minecraft first.")
    return names


def write_order(folder, names, allow_hidden=False):
    """Back up options.txt and atomically replace only resourcePacks fields."""
    if len(names) != len(set(names)):
        raise ValueError("Duplicate packs in order")
    for name in names:
        path = pack_path(folder, name)
        if not path.is_file() and not path.is_dir():
            raise ValueError(f"Pack not available: {name}")
    options, original, lines, old = _options(folder)
    # Keep built-in / modded entries such as programmer_art at their old positions.
    # Only ZIPs, existing folder packs and file/ entries belong to our editor.
    def editable(entry):
        return (entry.startswith("file/") or entry.lower().endswith(".zip")
                or _available(folder, entry)) if entry != "vanilla" else False

    existing = [entry.removeprefix("file/") for entry in old if editable(entry)]
    missing = [name for name in existing if not _available(folder, name) and not (
        allow_hidden and name.lower().endswith(".zip") and _available(folder, name + ".disabled"))]
    if missing:
        raise ValueError(f"Selected pack is unavailable: {missing[0]}. Restore it or change selection in Minecraft first.")
    prefix = "file/" if any(item.startswith("file/") for item in old) else ""
    remaining = iter(prefix + name for name in names)
    values = []
    for entry in old:
        if editable(entry):
            replacement = next(remaining, None)
            if replacement is not None:
                values.append(replacement)
        else:
            values.append(entry)
    values.extend(remaining)
    changed = []
    for line in lines:
        key, sep, _ = line.partition(":")
        if sep and key in ("resourcePacks", "oneconfig_legacy_resourcePacks"):
            changed.append(key + ":" + json.dumps(values, ensure_ascii=False, separators=(",", ":")) +
                           ("\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""))
        else:
            changed.append(line)
    result = "".join(changed).encode("utf-8")
    if result == original:
        return None
    backups = folder.parent / "pack-vault-backups"
    backups.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = backups / f"options-{stamp}.txt"
    shutil.copy2(options, backup)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=options.parent, prefix=".pack-vault-", delete=False) as output:
            temporary = Path(output.name)
            output.write(result)
        shutil.copymode(options, temporary)
        if options.read_bytes() != original:
            raise ValueError("Minecraft changed options.txt while saving. Close the game and try again.")
        os.replace(temporary, options)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return backup


def options_backups(folder):
    directory = folder.parent / "pack-vault-backups"
    if directory.is_symlink() or not directory.is_dir():
        return []
    return sorted((path for path in directory.iterdir()
                   if re.fullmatch(r"options-\d{8}-\d{6}-\d{6}\.txt", path.name)
                   and path.is_file() and not path.is_symlink()), reverse=True)


def restore_options_backup(folder, backup):
    """Restore an app-created snapshot; first save the current options for undo."""
    backup = Path(backup)
    if backup.is_symlink() or backup not in options_backups(folder):
        raise ValueError("Choose a Pack Vault options backup from this client")
    if backup.stat().st_size > 5 * 1024 * 1024:
        raise ValueError("Backup is too large")
    original_path = folder.parent / "options.txt"
    if original_path.is_symlink() or not original_path.is_file():
        raise ValueError("Minecraft options.txt is missing or is a symlink")
    original = original_path.read_bytes()
    saved = backup.read_bytes()
    try:
        text = saved.decode("utf-8")
        fields = [line for line in text.splitlines() if line.startswith("resourcePacks:")]
        entries = json.loads(fields[0].partition(":")[2]) if len(fields) == 1 else None
        if not isinstance(entries, list) or not all(isinstance(entry, str) for entry in entries):
            raise ValueError("Invalid resourcePacks in backup")
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Backup does not contain valid Minecraft options") from exc
    if original == saved:
        return None
    directory = backup.parent
    undo = directory / f"options-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.txt"
    shutil.copy2(original_path, undo)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=original_path.parent, prefix=".pack-vault-", delete=False) as output:
            temporary = Path(output.name)
            output.write(saved)
        shutil.copymode(original_path, temporary)
        if original_path.read_bytes() != original:
            raise ValueError("Minecraft changed options.txt while restoring. Close the game and try again.")
        os.replace(temporary, original_path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return undo
