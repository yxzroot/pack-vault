"""Profiles, pack overlap detection, and opt-in Modrinth update checks."""

from collections import defaultdict
import json
import re
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import zipfile

from app import pack_path, place_in_client, toggle


def enabled_zip_names(folder):
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if p.name.lower().endswith(".zip") and p.is_file())


def apply_profile(folder, names, library):
    """Set the available ZIPs in one client, rolling back on errors. Never delete existing packs."""
    wanted = set(names)
    if len(wanted) != len(names):
        raise ValueError("Duplicate ZIPs in profile")
    for name in wanted:
        pack_path(folder, name)
        if not name.lower().endswith(".zip"):
            raise ValueError("Profiles can only contain ZIP packs")
        enabled = folder / name
        hidden = folder / (name + ".disabled")
        if (enabled.exists() or enabled.is_symlink()) and not enabled.is_file():
            raise ValueError(f"{name} is not a ZIP pack")
        if hidden.exists() or hidden.is_symlink():
            if not hidden.is_file():
                raise ValueError(f"{name} is not a ZIP pack")
        elif not enabled.is_file():
            stored = pack_path(library, name)
            if not stored.is_file() or stored.is_symlink():
                raise ValueError(f"{name} is missing from the client and library")

    active = set(enabled_zip_names(folder))
    to_hide = sorted(active - wanted)
    to_show = sorted(wanted - active)
    changes = []
    try:
        for name in to_hide:
            toggle(folder, name)
            changes.append(("toggle", name + ".disabled"))
        for name in to_show:
            hidden = folder / (name + ".disabled")
            if hidden.is_file():
                toggle(folder, name + ".disabled")
                changes.append(("toggle", name))
            else:
                folder.mkdir(parents=True, exist_ok=True)
                place_in_client(pack_path(library, name), pack_path(folder, name))
                changes.append(("new", name))
    except Exception:
        for action, name in reversed(changes):
            if action == "toggle":
                toggle(folder, name)
            else:
                (folder / name).unlink()
        raise
    return {"hidden": to_hide, "enabled": to_show}


def scan_conflicts(folder, limit=50):
    """Report overlapping asset paths between enabled ZIPs; overlays may be intentional."""
    assets = defaultdict(list)
    if not folder.is_dir():
        return []
    for pack in sorted(folder.iterdir()):
        if not pack.name.lower().endswith(".zip") or not pack.is_file():
            continue
        try:
            with zipfile.ZipFile(pack) as archive:
                for entry in archive.infolist()[:100000]:
                    path = entry.filename.replace("\\", "/")
                    if not entry.is_dir() and path.startswith("assets/"):
                        assets[path].append(pack.name)
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile):
            continue
    return [(path, names) for path, names in sorted(assets.items()) if len(names) > 1][:limit]


def modrinth_slug(value):
    """Accept only a resourcepack URL or project slug; never fetch arbitrary URLs."""
    value = value.strip()
    if value.startswith("https://"):
        url = urlsplit(value)
        if url.netloc != "modrinth.com" or len(url.path.strip("/").split("/")) != 2:
            raise ValueError("Use a Modrinth resource-pack link")
        section, value = url.path.strip("/").split("/")
        if section != "resourcepack":
            raise ValueError("Use a Modrinth resource-pack link")
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", value):
        raise ValueError("Enter a Modrinth project slug or resource-pack link")
    return value


def latest_modrinth_version(slug):
    """Explicit, read-only request to Modrinth for a tracked resource pack."""
    slug = modrinth_slug(slug)
    headers = {"User-Agent": "PackVault/1.0 (https://github.com/yxzroot/pack-vault)"}
    def get_json(url):
        with urlopen(Request(url, headers=headers), timeout=8) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError("Modrinth response is too large")
            return json.loads(raw)

    project = get_json(f"https://api.modrinth.com/v2/project/{slug}")
    if project.get("project_type") != "resourcepack":
        raise ValueError(f"{slug} is not a Modrinth resource pack")
    versions = get_json(f"https://api.modrinth.com/v2/project/{slug}/version")
    if not versions:
        raise ValueError(f"{slug} has no published versions")
    latest = max(versions, key=lambda item: item["date_published"])
    return {"id": latest["id"], "number": latest["version_number"],
            "url": f"https://modrinth.com/resourcepack/{slug}/versions"}
