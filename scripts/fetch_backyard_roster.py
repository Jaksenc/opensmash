#!/usr/bin/env python3
"""Fetch backyarddesigners.club roster and prep opensmash inputs.

- Pulls the JSON-LD ItemList from /roster/ (no API needed, static site).
- Saves backyard/roster.json with name/handle/title/nick/bio/org/urls/images.
- Downloads -action.webp (best 3D ref, full-body) + -thumb.webp (face) into
  backyard/refs/<handle>_{action,thumb}.webp
- Writes backyard/names.txt (for scripts/batch_characters.py) and
  backyard/starter12.json (our curated 12 with base/emblem/notes).

Usage:
  python3 scripts/fetch_backyard_roster.py [--starter-only] [--refs-dir backyard/refs]
"""
import argparse
import json
import os
import re
import urllib.request

ROSTER_URL = "https://backyarddesigners.club/roster/"
ART = "https://backyarddesigners.club/roster-art/{handle}-{kind}.webp"

# handle -> (smash base, short label <=10 caps, emblem object, pipeline notes)
STARTER_12 = {
    "ridd_design":   ("mario",   "RIDD",     "a brown leather football", "commissioner, dive radio host, football in hands, sporty coach jacket"),
    "designertom":   ("luigi",   "LORE",     "a vintage film camera", "lorekeeper with load-bearing mustache, documentarian, green overshirt as luigi nod"),
    "raunofreiberg": ("fox",     "RAUNO",    "a pixel cursor arrow", "the detailer, vercel designer, obsessive micro-craft, sharp speedy fox energy"),
    "pablostanley":  ("kirby",   "PABLO",    "a paintbrush", "the illustrator, humaaans style modular character, playful pink-friendly outfit"),
    "joulee":        ("samus",   "ZHUO",     "an open book with glasses", "looking glass, ex-facebook VP turned author, composed tactician, visor-like glasses"),
    "lil_dill":      ("captain", "DILL",     "a striped checkout receipt", "the pilot, stripe head of design, fast falcon-like checkout flow energy"),
    "merycodes":     ("link",    "MERY",     "a drag handle with arrows", "drag handle, vercel design engineer, dashboard navigation, toolbelt with hooks"),
    "jh3yy":         ("pikachu", "JHEY",     "a lightning bolt plug", "the showman, builds interfaces then explains them, electric demo energy, yellow accent"),
    "apostraphi":    ("purin",   "PHI",      "a perplexity-style spark", "the figure-outer, perplexity creative studio, calm sing-like brand moment"),
    "vanschneider":  ("ness",    "TOBIAS",   "a small potted seedling", "the gardener, mymind digital garden, psychic ness vibe, thoughtful founder"),
    "robhope":       ("yoshi",   "ROB",      "a single folded web page", "above the fold, one page love archivist, surfer, egg-like single-page site capsule"),
    "darasoba":      ("donkey",  "DARA",     "a glowing beam cannon", "wildcard #1 beamer, heavy hitter, beam attacks, chunky streetwear"),
}

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fetch_roster():
    req = urllib.request.Request(ROSTER_URL, headers={"User-Agent": "DesignCrit/1.0"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="ignore")
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    data = json.loads(m.group(1))[0]["mainEntity"]["itemListElement"]
    out = []
    for it in data:
        p = it["item"]
        handle = p["url"].rstrip("/").split("/")[-1]
        out.append({
            "pos": it["position"],
            "handle": handle,
            "name": p["name"],
            "nick": p.get("alternateName"),
            "title": p.get("jobTitle"),
            "desc": p.get("description"),
            "org": (p.get("worksFor") or {}).get("name"),
            "url": p.get("url"),
            "img": p.get("image"),
            "sameAs": p.get("sameAs", []),
        })
    return out


def dl(url, dest):
    if os.path.exists(dest):
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "DesignCrit/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
        f.write(r.read())
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--starter-only", action="store_true")
    ap.add_argument("--refs-dir", default=os.path.join(HERE, "backyard", "refs"))
    ap.add_argument("--out", default=os.path.join(HERE, "backyard", "roster.json"))
    args = ap.parse_args()

    roster = fetch_roster()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(roster, open(args.out, "w"), indent=2, ensure_ascii=False)
    print(f"saved {len(roster)} designers -> {args.out}")

    wanted = set(STARTER_12) if args.starter_only else {r["handle"] for r in roster}
    names_path = os.path.join(HERE, "backyard", "names.txt" if not args.starter_only else "starter12-names.txt")
    starter_path = os.path.join(HERE, "backyard", "starter12.json")

    names = []
    starter = []
    by_handle = {r["handle"]: r for r in roster}
    for h in (STARTER_12 if args.starter_only else sorted(wanted)):
        r = by_handle.get(h)
        if not r:
            print(f"WARN missing {h}")
            continue
        # Wildcards only ship -sprite.webp (+ -og.png); others ship action/thumb.
        # Try action -> sprite -> thumb, save first hit as _{kind}.webp, track best photo.
        best_photo = None
        for kind in ("action", "sprite", "thumb"):
            try:
                dl(ART.format(handle=h, kind=kind),
                   os.path.join(args.refs_dir, f"{h}_{kind}.webp"))
                if best_photo is None:
                    best_photo = f"backyard/refs/{h}_{kind}.webp"
            except Exception as e:
                if kind == "action":
                    pass  # expected for wildcards, sprite fallback below
                else:
                    print(f"WARN {h} {kind}: {e}")
        if best_photo is None:  # last resort: -og.png share card
            try:
                dl(f"https://backyarddesigners.club/roster-art/{h}-og.png",
                   os.path.join(args.refs_dir, f"{h}_og.png"))
                best_photo = f"backyard/refs/{h}_og.png"
            except Exception as e:
                print(f"WARN {h} og: {e}")
                best_photo = f"backyard/refs/{h}_action.webp"
        names.append(r["name"])
        if h in STARTER_12:
            base, short, emblem, notes = STARTER_12[h]
            starter.append({
                "handle": h, "name": r["name"], "display": r["name"].split()[0][:12],
                "short": short, "base": base, "emblem": emblem, "notes": notes,
                "title": r["title"], "nick": r["nick"], "bio": r["desc"],
                "photo": best_photo,
            })

    open(names_path, "w").write("\n".join(names) + "\n")
    json.dump(starter, open(starter_path, "w"), indent=2, ensure_ascii=False)
    print(f"wrote {names_path} ({len(names)}) + {starter_path} ({len(starter)})")
    print("\nNext:")
    print("  python3 pipeline/run_character.py \"Rauno Freiberg\" --photo backyard/refs/raunofreiberg_action.webp --short RAUNO --emblem \"a pixel cursor arrow\" --notes \"...\" --variants all")


if __name__ == "__main__":
    main()
