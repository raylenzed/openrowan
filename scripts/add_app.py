#!/usr/bin/env python3
"""Register a new app on openrowan.com.

Writes data/apps/<slug>.yaml with `status: coming_soon`, creates
content/apps/<slug>/_index.md, and, when --icon is given, a 256 px local icon
shown until the app is live. Once App Review approves the app,
scripts/sync_apps.py (run daily by GitHub Actions) adds the App Store link,
price, icon and screenshots, and the app appears as live.

Example:
  python3 scripts/add_app.py --slug encore --name Encore --category home \\
    --tagline "Remote for Harmony Hub" --bundle-id com.raylenzed.encore \\
    --asc-app-id 6828364879 --unlock-price '$7.99' \\
    --icon ../ios-apps/Encore/Encore/Assets.xcassets/AppIcon.appiconset/AppIcon.png
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_apps import APPS_DIR, IMG_DIR, ROOT, category_ids, load_yaml  # noqa: E402

CONTENT_DIR = ROOT / "content" / "apps"


def quoted(value):
    # A JSON string is also a valid YAML double-quoted scalar.
    return json.dumps(value, ensure_ascii=False)


def next_order(category):
    orders = [int(app.get("order") or 0) for app in map(load_yaml, APPS_DIR.glob("*.yaml")) if app.get("category") == category]
    return max(orders, default=0) + 10


def make_icon(source, slug):
    dest = IMG_DIR / f"{slug}-local.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("sips"):
        subprocess.run(["sips", "-s", "format", "png", "-Z", "256", str(source), "--out", str(dest)], check=True, capture_output=True)
    else:
        try:
            from PIL import Image
        except ImportError:
            shutil.copyfile(source, dest)
            print("warning: neither sips nor Pillow found; copied the icon without resizing")
        else:
            with Image.open(source) as image:
                image.thumbnail((256, 256))
                image.save(dest, "PNG")
    return f"/images/apps/{dest.name}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--slug", required=True, help="URL slug, the same one used in content/apps/<slug>/ (e.g. henLog)")
    parser.add_argument("--name", required=True, help="short display name, e.g. HenLog")
    parser.add_argument("--category", required=True, help="one of the ids in data/categories.yaml")
    parser.add_argument("--tagline", required=True, help="one line in English, e.g. 'Flock and egg tracker'")
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--asc-app-id", required=True, help="App Store Connect app id (digits)")
    parser.add_argument("--storefront", default="us", help="App Store country used for links and prices (default: us)")
    parser.add_argument("--unlock-price", default="", help="in-app unlock price for free downloads, e.g. '$5.99'")
    parser.add_argument("--store-label", default="", help="shown after the price, e.g. 'China' for a China-only app")
    parser.add_argument("--order", type=int, help="position inside the category (default: last)")
    parser.add_argument("--featured", action="store_true")
    parser.add_argument("--icon", type=Path, help="1024 px AppIcon.png from the Xcode project")
    parser.add_argument("--force", action="store_true", help="overwrite an existing data/apps/<slug>.yaml")
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", args.slug):
        parser.error("--slug must be letters and digits, starting with a letter")
    if args.category not in category_ids():
        parser.error(f"--category must be one of {sorted(category_ids())}")
    if not args.asc_app_id.isdigit():
        parser.error("--asc-app-id must be digits")
    data_path = APPS_DIR / f"{args.slug}.yaml"
    if data_path.exists() and not args.force:
        parser.error(f"{data_path.relative_to(ROOT)} already exists (use --force to overwrite)")

    lines = [
        "# Editorial fields, written by scripts/add_app.py or by hand.",
        "# App Store fields (price, link, icon, screenshots, version) live in",
        "# data/store/<slug>.json and are refreshed daily by scripts/sync_apps.py.",
        f"name: {quoted(args.name)}",
        f"slug: {quoted(args.slug)}",
        f"bundle_id: {quoted(args.bundle_id)}",
        f"asc_app_id: {quoted(args.asc_app_id)}",
        f"storefront: {quoted(args.storefront)}",
        'status: "coming_soon"   # coming_soon | live | hidden; sync shows it as live once it is on the App Store',
        f"category: {quoted(args.category)}",
        f"tagline: {quoted(args.tagline)}",
        f"featured: {'true' if args.featured else 'false'}",
        f"order: {args.order if args.order is not None else next_order(args.category)}",
        f"unlock_price: {quoted(args.unlock_price)}",
    ]
    if args.store_label:
        lines.append(f"store_label: {quoted(args.store_label)}")
    if args.icon:
        lines.append(f"local_icon: {quoted(make_icon(args.icon, args.slug))}")
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {data_path.relative_to(ROOT)}")

    index_path = CONTENT_DIR / args.slug / "_index.md"
    if not index_path.exists():
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(f"---\ntitle: {quoted(args.name)}\n---\n", encoding="utf-8")
        print(f"wrote {index_path.relative_to(ROOT)}")

    print("next: add privacy.md and support.md under content/apps/<slug>/, then commit and push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
