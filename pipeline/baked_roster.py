#!/usr/bin/env python3
"""Validate and publish a manually generated fighter to the baked roster."""

import argparse
import json
import os
import re
import tempfile


PIPELINE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MANIFEST = os.path.join(PIPELINE_ROOT, "web-prototype", "config", "characters.json")
SLUG_PATTERN = re.compile(r"^[a-z0-9]+$")


def validate_character(slug, pipeline_root=PIPELINE_ROOT):
    if not SLUG_PATTERN.fullmatch(slug):
        raise ValueError(f"invalid baked character slug: {slug!r}")

    ui_root = os.path.join(pipeline_root, "play", "ui", slug)
    required = [
        os.path.join(pipeline_root, "play", f"{slug}.osb6"),
        os.path.join(ui_root, "character.json"),
        os.path.join(ui_root, "portrait_raw.png"),
        os.path.join(ui_root, "portrait_tile.png"),
        os.path.join(ui_root, "portrait_medium.png"),
        os.path.join(ui_root, f"{slug}.osbui"),
        os.path.join(ui_root, "announcer.wav"),
    ]
    missing = [os.path.relpath(path, pipeline_root) for path in required if not os.path.isfile(path)]
    if missing:
        raise RuntimeError("cannot publish incomplete baked character; missing: " + ", ".join(missing))

    with open(os.path.join(ui_root, "character.json"), encoding="utf-8") as source:
        metadata = json.load(source)
    if not metadata.get("display"):
        raise RuntimeError(f"play/ui/{slug}/character.json has no display name")


def publish_character(slug, pipeline_root=PIPELINE_ROOT, manifest_path=DEFAULT_MANIFEST):
    validate_character(slug, pipeline_root)
    with open(manifest_path, encoding="utf-8") as source:
        manifest = json.load(source)
    if not isinstance(manifest, list):
        raise RuntimeError("baked character manifest must be an array")

    existing = [entry if isinstance(entry, str) else entry.get("slug") for entry in manifest]
    if slug in existing:
        return False
    manifest.append({"slug": slug})

    directory = os.path.dirname(manifest_path)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, delete=False) as output:
        json.dump(manifest, output, indent=2)
        output.write("\n")
        temporary = output.name
    os.replace(temporary, manifest_path)
    os.chmod(manifest_path, 0o644)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="validated character slug to add to the baked manifest")
    args = parser.parse_args()
    changed = publish_character(args.slug)
    print(f"{'Published' if changed else 'Already published'} baked character: {args.slug}")


if __name__ == "__main__":
    main()
