#!/usr/bin/env python3
"""Refresh App Store data for the apps listed in data/apps/*.yaml.

For every app with an `asc_app_id`, look it up on the public iTunes Search API
(no credentials needed) in the app's `storefront`, then write:

  data/store/<slug>.json               store name, price, link, version, summary, features
  static/images/apps/<slug>.webp       256 px icon
  static/images/apps/<slug>-<n>.webp   up to 3 iPhone screenshots, 600 px wide

Editorial files in data/apps/ are never modified. Files are rewritten only when
their content changes, so a run with no App Store changes leaves git clean.

Usage:
  python3 scripts/sync_apps.py           # sync from the App Store
  python3 scripts/sync_apps.py --check   # validate the data files, no network
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPS_DIR = ROOT / "data" / "apps"
STORE_DIR = ROOT / "data" / "store"
IMG_DIR = ROOT / "static" / "images" / "apps"
CATEGORIES_FILE = ROOT / "data" / "categories.yaml"

STATUSES = {"coming_soon", "live", "hidden"}
LOOKUP_URL = "https://itunes.apple.com/lookup"
# Apple's image CDN renders any size and format named in the last path segment.
SIZE_SEGMENT = re.compile(r"/[^/]+\.(?:jpg|jpeg|png|webp)$")
ICON_SEGMENT = "/256x256bb.webp"
SHOT_SEGMENT = "/600x0w.webp"
MAX_SHOTS = 3
MAX_FEATURES = 8


def parse_flat_yaml(text):
    """Read top-level `key: value` pairs. Enough for the fields this script needs
    when PyYAML is not installed."""
    data = {}
    for line in text.splitlines():
        if not line or line[0] in " \t#-":
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        value = value.split(" #", 1)[0].strip()
        if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]
        elif value in ("true", "false"):
            value = value == "true"
        elif re.fullmatch(r"-?\d+", value):
            value = int(value)
        data[key.strip()] = value
    return data


def load_yaml(path):
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ImportError:
        return parse_flat_yaml(text)
    return yaml.safe_load(text) or {}


def category_ids():
    return set(re.findall(r"^\s*-\s*id:\s*\"?([A-Za-z0-9_-]+)", CATEGORIES_FILE.read_text(encoding="utf-8"), re.M))


def load_apps():
    apps = {}
    for path in sorted(APPS_DIR.glob("*.yaml")):
        app = load_yaml(path)
        app["_file"] = path
        apps[path.stem] = app
    return apps


def fetch(url, attempts=3):
    request = urllib.request.Request(url, headers={"User-Agent": "openrowan-site-sync/1.0"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(2 * (attempt + 1))


def lookup(app_ids, country):
    query = urllib.parse.urlencode({"id": ",".join(app_ids), "country": country, "entity": "software"})
    data = json.loads(fetch(f"{LOOKUP_URL}?{query}"))
    return {str(r["trackId"]): r for r in data.get("results", []) if "trackId" in r}


def split_description(description):
    blocks = [b.strip() for b in re.split(r"\n\s*\n", description or "") if b.strip()]
    summary = blocks[0] if blocks else ""
    features = []
    for line in (description or "").splitlines():
        line = line.strip()
        if len(line) > 2 and line[0] in "•–-*":
            features.append(line[1:].strip())
            if len(features) == MAX_FEATURES:
                break
    return summary, features


def price_label(result):
    if not result.get("price"):
        return "Free"
    return re.sub(r"\.00$", "", result.get("formattedPrice") or "")


def write_if_changed(path, data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def sync_app(slug, result, changed):
    store_path = STORE_DIR / f"{slug}.json"
    previous = json.loads(store_path.read_text(encoding="utf-8")) if store_path.exists() else {}

    icon_source = SIZE_SEGMENT.sub(ICON_SEGMENT, result.get("artworkUrl512") or result.get("artworkUrl100") or "")
    icon_path = IMG_DIR / f"{slug}.webp"
    if icon_source and (icon_source != previous.get("icon_source") or not icon_path.exists()):
        if write_if_changed(icon_path, fetch(icon_source)):
            changed.append(str(icon_path.relative_to(ROOT)))

    shot_sources = [SIZE_SEGMENT.sub(SHOT_SEGMENT, u) for u in (result.get("screenshotUrls") or [])[:MAX_SHOTS]]
    shots = []
    for n, source in enumerate(shot_sources, 1):
        shot_path = IMG_DIR / f"{slug}-{n}.webp"
        old_sources = previous.get("screenshot_sources") or []
        if n > len(old_sources) or old_sources[n - 1] != source or not shot_path.exists():
            if write_if_changed(shot_path, fetch(source)):
                changed.append(str(shot_path.relative_to(ROOT)))
        shots.append(f"/images/apps/{slug}-{n}.webp")
    for stale in IMG_DIR.glob(f"{slug}-*.webp"):
        index = stale.stem.rsplit("-", 1)[-1]
        if index.isdigit() and int(index) > len(shot_sources):
            stale.unlink()
            changed.append(str(stale.relative_to(ROOT)))

    summary, features = split_description(result.get("description"))
    record = {
        "store_name": result.get("trackName", ""),
        "price": price_label(result),
        "appstore_url": (result.get("trackViewUrl") or "").split("?")[0],
        "version": result.get("version", ""),
        "updated": (result.get("currentVersionReleaseDate") or "")[:10],
        "released": (result.get("releaseDate") or "")[:10],
        "genre": result.get("primaryGenreName", ""),
        "min_ios": result.get("minimumOsVersion", ""),
        "summary": summary,
        "features": features,
        "icon": f"/images/apps/{slug}.webp" if icon_source else "",
        "screenshots": shots,
        "icon_source": icon_source,
        "screenshot_sources": shot_sources,
    }
    if write_if_changed(store_path, json.dumps(record, ensure_ascii=False, indent=2) + "\n"):
        changed.append(str(store_path.relative_to(ROOT)))


def validate(apps):
    problems = []
    categories = category_ids()
    for slug, app in apps.items():
        status = app.get("status")
        if app.get("slug") != slug:
            problems.append(f"{slug}: `slug` must match the file name")
        if status not in STATUSES:
            problems.append(f"{slug}: `status` must be one of {sorted(STATUSES)}")
            continue
        if status == "hidden":
            continue
        for field in ("name", "tagline", "category"):
            if not app.get(field):
                problems.append(f"{slug}: missing `{field}`")
        if app.get("category") and app["category"] not in categories:
            problems.append(f"{slug}: unknown category `{app['category']}` (see data/categories.yaml)")
        store_path = STORE_DIR / f"{slug}.json"
        if status == "live" and not store_path.exists():
            problems.append(f"{slug}: live but has no App Store data yet; run scripts/sync_apps.py")
        if store_path.exists():
            icon = json.loads(store_path.read_text(encoding="utf-8")).get("icon")
            if icon and not (ROOT / "static" / icon.lstrip("/")).exists():
                problems.append(f"{slug}: icon file {icon} is missing")
        elif app.get("local_icon") and not (ROOT / "static" / str(app["local_icon"]).lstrip("/")).exists():
            problems.append(f"{slug}: local_icon {app['local_icon']} is missing")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="validate the data files without network access")
    args = parser.parse_args()

    apps = load_apps()
    if args.check:
        problems = validate(apps)
        for problem in problems:
            print(f"error: {problem}")
        print(f"checked {len(apps)} apps, {len(problems)} problem(s)")
        return 1 if problems else 0

    by_country = {}
    for slug, app in apps.items():
        if app.get("asc_app_id") and app.get("status") != "hidden":
            by_country.setdefault(str(app.get("storefront") or "us"), []).append((slug, str(app["asc_app_id"])))

    changed = []
    for country, entries in sorted(by_country.items()):
        results = lookup([app_id for _, app_id in entries], country)
        for slug, app_id in entries:
            result = results.get(app_id)
            if result:
                sync_app(slug, result, changed)
            elif apps[slug].get("status") == "live":
                print(f"warning: {slug} ({app_id}) not found on the {country} App Store; keeping old data")

    for path in changed:
        print(f"updated {path}")
    print(f"synced {sum(len(e) for e in by_country.values())} apps, {len(changed)} file(s) changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
