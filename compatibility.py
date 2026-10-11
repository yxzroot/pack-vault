"""Conservative Java Edition resource-pack version checks and copy-only conversion."""

from copy import copy
from itertools import islice
import json
import re
import shutil
import zipfile

from app import MAX_UPLOAD, pack_path, zip_member


# Released Java Edition RESOURCE pack formats (not data-pack formats).
# https://minecraft.wiki/w/Pack_format#Resource_pack_format_history
# Explicit releases avoid guessing the format for a snapshot or nonexistent patch.
_RELEASES = (
    (1, "1.6.1 1.6.2 1.6.4 1.7.2 1.7.4 1.7.5 1.7.6 1.7.7 1.7.8 1.7.9 1.7.10 "
        "1.8 1.8.1 1.8.2 1.8.3 1.8.4 1.8.5 1.8.6 1.8.7 1.8.8 1.8.9"),
    (2, "1.9 1.9.1 1.9.2 1.9.3 1.9.4 1.10 1.10.1 1.10.2"),
    (3, "1.11 1.11.1 1.11.2 1.12 1.12.1 1.12.2"),
    (4, "1.13 1.13.1 1.13.2 1.14 1.14.1 1.14.2 1.14.3 1.14.4"),
    (5, "1.15 1.15.1 1.15.2 1.16 1.16.1"),
    (6, "1.16.2 1.16.3 1.16.4 1.16.5"),
    (7, "1.17 1.17.1"),
    (8, "1.18 1.18.1 1.18.2"),
    (9, "1.19 1.19.1 1.19.2"),
    (12, "1.19.3"), (13, "1.19.4"),
    (15, "1.20 1.20.1"), (18, "1.20.2"), (22, "1.20.3 1.20.4"),
    (32, "1.20.5 1.20.6"), (34, "1.21 1.21.1"),
    (42, "1.21.2 1.21.3"), (46, "1.21.4"), (55, "1.21.5"),
    (63, "1.21.6"), (64, "1.21.7 1.21.8"),
    (69.0, "1.21.9 1.21.10"), (75.0, "1.21.11"),
    (84.0, "26.1 26.1.1 26.1.2"), (88.0, "26.2"), (97.1, "26.3"),
)
FORMATS = {version: format_number for format_number, releases in _RELEASES
           for version in releases.split()}


def version_from_text(value):
    match = re.search(r"(?<![\d.])((?:1\.(?:[6-9]|1\d|20|21)|26\.\d+)(?:\.\d+)?)(?![\d.])", value)
    return match.group(1) if match and match.group(1) in FORMATS else None


def detect_game_version(folder):
    """Return a version only when launcher metadata gives an unambiguous answer."""
    game = folder.parent
    for root in (game, game.parent):
        prism = root / "mmc-pack.json"
        if prism.is_file():
            try:
                components = json.loads(prism.read_text()).get("components", [])
                versions = {version_from_text(item.get("version", "")) for item in components
                            if item.get("uid") == "net.minecraft"}
                versions.discard(None)
                if len(versions) == 1:
                    return versions.pop()
            except (OSError, ValueError, TypeError, AttributeError):
                pass
        modrinth = root / "profile.json"
        if modrinth.is_file():
            try:
                version = json.loads(modrinth.read_text()).get("game_version", "")
                if isinstance(version, str) and version_from_text(version):
                    return version_from_text(version)
            except (OSError, ValueError, TypeError, AttributeError):
                pass
    oneclient_versions = game.parent / "metadata/versions"
    if game.name == ".minecraft" and oneclient_versions.is_dir():
        versions = {version_from_text(path.name) for path in oneclient_versions.iterdir() if path.is_dir()}
        versions.discard(None)
        if len(versions) == 1:
            return versions.pop()
    for cfg in (game / "instance.cfg", game.parent / "instance.cfg"):
        if cfg.is_file():
            for line in cfg.read_text(errors="replace").splitlines():
                if line.startswith("IntendedVersion="):
                    return version_from_text(line)
    profile = game / "launcher_profiles.json"
    if profile.is_file():
        try:
            data = json.loads(profile.read_text())
            selected = data.get("profiles", {}).get(data.get("selectedProfile"), {})
            return version_from_text(selected.get("lastVersionId", ""))
        except (OSError, ValueError, AttributeError):
            pass
    versions_dir = game / "versions"
    if versions_dir.is_dir():
        versions = {version_from_text(path.name) for path in versions_dir.iterdir() if path.is_dir()}
        versions.discard(None)
        if len(versions) == 1:
            return versions.pop()
    return None


def _metadata(path):
    if path.is_dir():
        meta = path / "pack.mcmeta"
        if not meta.is_file() or meta.stat().st_size > 2 * 1024 * 1024:
            return None
        raw = meta.read_bytes()
    else:
        with zipfile.ZipFile(path) as archive:
            raw = zip_member(archive, "pack.mcmeta")
    document = json.loads(raw) if raw else None
    if isinstance(document, dict) and isinstance(document.get("pack"), dict):
        return document["pack"]
    return None


def _format_value(value):
    """Return (major, minor); modern formats are JSON integer pairs, never floats."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value, 0
    if (isinstance(value, list) and len(value) in (1, 2) and
            all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in value)):
        return value[0], value[1] if len(value) == 2 else 0
    return None


def _format_label(value):
    return value[0] if value[1] == 0 else f"{value[0]}.{value[1]}"


def pack_format(path):
    try:
        pack = _metadata(path)
        number = _format_value(pack.get("min_format", pack.get("pack_format"))) if pack else None
        return _format_label(number) if number else None
    except (OSError, ValueError, KeyError, RuntimeError, NotImplementedError,
            zipfile.BadZipFile, UnicodeError):
        return None


def pack_supports(path, version):
    """Check declared metadata ranges; a matching number is not a gameplay guarantee."""
    if version not in FORMATS:
        return None
    target = _format_value(FORMATS[version])
    # FORMATS stores decimal display values for recent releases; convert explicitly.
    if target is None:
        major, _, minor = str(FORMATS[version]).partition(".")
        target = (int(major), int(minor))
    try:
        pack = _metadata(path)
    except (OSError, ValueError, KeyError, RuntimeError, NotImplementedError,
            zipfile.BadZipFile, UnicodeError):
        return None
    if pack is None:
        return None
    lower, upper = _format_value(pack.get("min_format")), _format_value(pack.get("max_format"))
    if lower and upper:
        # An integer max_format means all minor revisions of that major version.
        if isinstance(pack.get("max_format"), int):
            upper = (upper[0], 2**31 - 1)
        return lower <= target <= upper
    supported = pack.get("supported_formats")
    if isinstance(supported, dict):
        minimum = _format_value(supported.get("min_inclusive"))
        maximum = _format_value(supported.get("max_inclusive"))
    elif isinstance(supported, list) and len(supported) == 2:
        minimum, maximum = map(_format_value, supported)
    else:
        minimum = maximum = _format_value(supported)
    if minimum and maximum:
        return minimum <= target <= maximum
    declared = _format_value(pack.get("pack_format"))
    return declared == target if declared else None


def texture_previews(path, limit=5):
    """Read a few small PNGs for the preview dialog; never extract the archive."""
    preferred = ("pack.png", "assets/minecraft/textures/block/stone.png",
                 "assets/minecraft/textures/blocks/stone.png",
                 "assets/minecraft/textures/item/diamond_sword.png",
                 "assets/minecraft/textures/items/diamond_sword.png")
    try:
        if path.is_dir():
            candidates = list(islice((p for p in path.rglob("*.png") if p.is_file() and
                                      (p.name == "pack.png" or "textures" in p.parts)), 100))
            candidates.sort(key=lambda p: (str(p.relative_to(path)) not in preferred, str(p)))
            return [(str(p.relative_to(path)), p.read_bytes()) for p in candidates
                    if p.stat().st_size <= 2 * 1024 * 1024][:limit]
        with zipfile.ZipFile(path) as archive:
            candidates = [info for info in archive.infolist()[:10000] if info.filename.endswith(".png")
                          and info.file_size <= 2 * 1024 * 1024 and
                          (info.filename == "pack.png" or "/textures/" in info.filename)]
            candidates.sort(key=lambda i: (i.filename not in preferred, i.filename))
            return [(info.filename, archive.read(info)) for info in candidates[:limit]]
    except (OSError, ValueError, RuntimeError, NotImplementedError, zipfile.BadZipFile):
        return []


def convert_pack(source, version, library, report=None):
    """Create a new ZIP; retarget metadata and alias legacy block/item texture folders only."""
    if version not in FORMATS:
        raise ValueError("Choose a supported Minecraft release")
    if source.stat().st_size > MAX_UPLOAD:
        raise ValueError("ZIP exceeds 128 MB limit")
    target_format = FORMATS[version]
    major, _, minor = str(target_format).partition(".")
    target_pair = int(major), int(minor) if minor else 0
    with zipfile.ZipFile(source) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Pack ZIP contains duplicate paths; cannot convert it safely")
        try:
            info = archive.getinfo("pack.mcmeta")  # require metadata at ZIP root
        except KeyError as exc:
            raise ValueError("Pack ZIP needs pack.mcmeta at its root") from exc
        if info.file_size > 2 * 1024 * 1024:
            raise ValueError("Pack metadata is too large")
        metadata = json.loads(archive.read(info))
        if not isinstance(metadata, dict) or not isinstance(metadata.get("pack"), dict):
            raise ValueError("Missing pack metadata")
        source_format = _format_value(metadata["pack"].get("min_format", metadata["pack"].get("pack_format")))
        if source_format is None:
            raise ValueError("Source pack has no valid resource-pack format")
        if target_format >= 69:
            # Releases since 1.21.9 use min_format/max_format in place of pack_format.
            metadata["pack"].pop("pack_format", None)
            metadata["pack"]["min_format"] = list(target_pair)
            metadata["pack"]["max_format"] = list(target_pair)
        else:
            metadata["pack"]["pack_format"] = target_format
            metadata["pack"].pop("min_format", None)
            metadata["pack"].pop("max_format", None)
        # Old Minecraft doesn't understand newer compatibility/overlay metadata.
        metadata["pack"].pop("supported_formats", None)
        removed_overlays = "overlays" in metadata and (target_format < 18 or source_format != target_pair)
        if target_format < 18 or source_format != target_pair:
            metadata.pop("overlays", None)

        stem = source.stem[:90]
        name = f"{stem}-for-{version}.zip"
        destination = pack_path(library, name)
        if destination.exists() or destination.is_symlink():
            raise ValueError(f"Converted pack already exists: {name}")
        library.mkdir(parents=True, exist_ok=True)
        created = False
        try:
            with destination.open("xb") as output:
                created = True
                with zipfile.ZipFile(output, "w") as result:
                    seen = set(names)
                    total = 0
                    aliases = []
                    collisions = 0
                    unconverted = {"models": 0, "shaders": 0, "sounds": 0}
                    for member in archive.infolist():
                        total += member.file_size
                        if total > 512 * 1024 * 1024:
                            raise ValueError("Pack would expand beyond 512 MB")
                        if member.filename == "pack.mcmeta":
                            result.writestr("pack.mcmeta", json.dumps(metadata, ensure_ascii=False, indent=2))
                            continue
                        if member.is_dir():
                            result.writestr(copy(member), b"")
                            continue
                        if "/models/" in member.filename and member.filename.endswith(".json"):
                            unconverted["models"] += 1
                        if "/shaders/" in member.filename:
                            unconverted["shaders"] += 1
                        if "/sounds/" in member.filename:
                            unconverted["sounds"] += 1
                        # ZipFile mutates ZipInfo.header_offset while writing: never pass
                        # the source's ZipInfo object into the destination archive.
                        with archive.open(member) as src, result.open(copy(member), "w") as dst:
                            shutil.copyfileobj(src, dst, length=64 * 1024)
                        # Add aliases rather than rename: custom models might still refer to old paths.
                        old = "/textures/blocks/" if source_format[0] < 4 and target_format >= 4 else "/textures/block/"
                        new = "/textures/block/" if old.endswith("blocks/") else "/textures/blocks/"
                        if (((source_format[0] < 4 <= target_format) or (target_format < 4 <= source_format[0])) and
                                member.filename.startswith("assets/") and old in member.filename):
                            alias = member.filename.replace(old, new, 1)
                            if alias not in seen:
                                aliases.append((member.filename, alias))
                                seen.add(alias)
                            else:
                                collisions += 1
                        old_item = old.replace("block", "item")
                        new_item = new.replace("block", "item")
                        if (((source_format[0] < 4 <= target_format) or (target_format < 4 <= source_format[0])) and
                                member.filename.startswith("assets/") and old_item in member.filename):
                            alias = member.filename.replace(old_item, new_item, 1)
                            if alias not in seen:
                                aliases.append((member.filename, alias))
                                seen.add(alias)
                            else:
                                collisions += 1
                    for original, alias in aliases:
                        total += archive.getinfo(original).file_size
                        if total > 512 * 1024 * 1024:
                            raise ValueError("Converted pack would expand beyond 512 MB")
                        with archive.open(original) as src, result.open(alias, "w") as dst:
                            shutil.copyfileobj(src, dst, length=64 * 1024)
        except Exception:
            if created:
                destination.unlink(missing_ok=True)
            raise
    if report is not None:
        report.update({"source_format": _format_label(source_format),
                       "target_format": _format_label(target_pair),
                       "aliases": [alias for _, alias in aliases],
                       "alias_collisions": collisions, "removed_overlays": removed_overlays,
                       "unchanged": unconverted})
    return destination
