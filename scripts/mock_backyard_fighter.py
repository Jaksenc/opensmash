#!/usr/bin/env python3
"""Offline backyard fighter prep — no API keys, no ROM, no engine.

Creates everything the full pipeline needs EXCEPT the paid/generated bits:
  play/ui/<slug>/character.json  (display/short/desc/emblem/base/position)
  play/ui/<slug>/cost.json        ($0 dry-run ledger)
  play/ui/<slug>/portrait_raw.png + portrait_tile.png + portrait_medium.png
    (converted from backyard/refs/<handle>_{action,sprite,thumb}.webp via PIL;
    falls back to a byte copy renamed to .png if PIL is missing)
  play/ui/<slug>/announcer.txt    (text the announcer WILL say once FAL_KEY is set)

It deliberately does NOT fake <slug>.osb6 / .osbui / announcer.wav — those need
Tripo mesh + engine convert + MiniMax TTS. baked_roster.py will still report
the slug as incomplete, which is the honest signal.

Usage:
  python3 scripts/mock_backyard_fighter.py --all
  python3 scripts/mock_backyard_fighter.py raunofreiberg
  python3 scripts/mock_backyard_fighter.py --handle raunofreiberg
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STARTER = os.path.join(HERE, "backyard", "starter12.json")
CONFIG = os.path.join(HERE, "web-prototype", "config", "backyard-starter.json")
ROSTER = os.path.join(HERE, "backyard", "roster.json")

import re

def pipeline_slug(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())[:16]


def load_entries():
    starter = json.load(open(STARTER))
    roster = {r["handle"]: r for r in json.load(open(ROSTER))}
    config = {c["handle"]: c for c in json.load(open(CONFIG))}
    merged = []
    for e in starter:
        c = config.get(e["handle"], {})
        merged.append({**e, **{k: v for k, v in c.items() if k not in e},
                       "slug": c.get("slug") or pipeline_slug(e["name"])})
    return merged, roster


def convert_art(src, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        return dest
    try:
        from PIL import Image
        img = Image.open(src).convert("RGB")
        img.save(dest, "PNG")
        return dest
    except ImportError:
        shutil.copyfile(src, dest)
        print(f"  (PIL missing, copied {src} -> {dest} without transcode)", file=sys.stderr)
        return dest
    except Exception as e:
        print(f"  WARN art convert {src}: {e}", file=sys.stderr)
        return None


def mock_one(entry, bio):
    slug = entry["slug"]
    out = os.path.join(HERE, "play", "ui", slug)
    os.makedirs(out, exist_ok=True)

    desc = (
        f"{entry['display']} ({entry['nick']}): {entry['position']} at "
        f"{bio.get('org', '?')}. {bio.get('desc', '')} "
        f"ONE iconic outfit, flat solid colors, empty hands, fitted clothes, "
        f"mouth closed. Emblem: {entry['emblem']}."
    )[:900]
    character = {
        "display": entry["display"],
        "short": entry["short"],
        "desc": desc,
        "emblem": entry["emblem"],
        "name_full": bio.get("name", entry["display"]),
        "base": entry["base"],
        "preferred_bases": entry.get("preferredBases", [entry["base"]]),
        "position": entry["position"],
        "handle": entry["handle"],
        "roster_url": entry.get("rosterUrl"),
        "refs": [],
        "cost_usd": 0.0,
        "mock": True,
    }
    json.dump(character, open(os.path.join(out, "character.json"), "w"), indent=2)
    json.dump({"mock": True, "expand": 0, "tpose": 0, "mesh": 0, "voice": 0},
              open(os.path.join(out, "cost.json"), "w"), indent=2)
    open(os.path.join(out, "announcer.txt"), "w").write(entry["display"] + "\n")

    photo = os.path.join(HERE, entry.get("photo", f"backyard/refs/{entry['handle']}_action.webp"))
    if not os.path.exists(photo):
        for cand in (f"backyard/refs/{entry['handle']}_sprite.webp",
                     f"backyard/refs/{entry['handle']}_thumb.webp",
                     f"backyard/refs/{entry['handle']}_og.png"):
            if os.path.exists(os.path.join(HERE, cand)):
                photo = os.path.join(HERE, cand)
                break
    if os.path.exists(photo):
        for name in ("portrait_raw.png", "portrait_tile.png", "portrait_medium.png"):
            convert_art(photo, os.path.join(out, name))
    else:
        print(f"  WARN no ref art for {entry['handle']}", file=sys.stderr)

    print(f"mocked {slug} <- {entry['handle']} ({entry['base']}, {entry['position']})")
    return slug


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", nargs="?", help="starter slug e.g. raunofreiberg")
    ap.add_argument("--handle", help="backyard handle e.g. raunofreiberg")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    starter, roster = load_entries()
    if args.all:
        want = starter
    elif args.handle:
        want = [e for e in starter if e["handle"] == args.handle]
    elif args.slug:
        want = [e for e in starter if e["slug"] == args.slug or e["handle"] == args.slug]
    else:
        want = [e for e in starter if e["slug"] == "raunofreiberg"]

    if not want:
        print("no matching starter (try --all or a slug from backyard/starter12.json)", file=sys.stderr)
        sys.exit(1)
    for entry in want:
        mock_one(entry, roster.get(entry["handle"], {}))
    print(f"\nDone: {len(want)} mocked. Next (needs keys + ROM + BattleShip build):")
    print("  python3 pipeline/run_character.py \"<Name>\" --photo <ref> --short X --emblem \"...\" --notes \"...\" --variants all")


if __name__ == "__main__":
    main()
