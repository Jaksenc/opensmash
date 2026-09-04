#!/usr/bin/env python3
"""Backyard sprite packs — zero API keys, zero ROM, fully deterministic.

For each starter-12 fighter, builds from the downloaded backyard cartoon art:
  play/ui/<slug>/portrait_raw.png   (square, from thumb/action webp)
  play/ui/<slug>/portrait_tile.png + portrait_medium.png (via portrait_tiles.py)
  play/ui/<slug>/emblem_raw.png     (initial-letter stencil art, PIL-drawn)
  play/ui/<slug>/<slug>.osbui       (real engine UI pack via gen_ui_assets.py)
  play/ui/<slug>/preview.png        (.osbui preview render)

Stock icon comes straight from the thumb (--stock-art); the backyard art's
flat backgrounds key out with the pipeline's own key_bg.

Run with the project venv (needs Pillow/numpy/scipy):
  .venv/bin/python scripts/backyard_sprites.py [--slug X] [--force]

Upgrade path: replace portrait_raw/stock/emblem_raw with gpt-image-2 outputs
(pipeline/run_character.py stages portrait/stock/emblem) and re-run this
script — the .osbui rebuild is free and local.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(HERE, "web-prototype", "config", "backyard-starter.json")
REFS = os.path.join(HERE, "backyard", "refs")
PIPE = os.path.join(HERE, "pipeline")


def sh(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:4])} failed: {(r.stderr or r.stdout)[-2000:]}")
    return r.stdout


def ref_for(handle):
    for kind in ("thumb", "action", "sprite"):
        p = os.path.join(REFS, f"{handle}_{kind}.webp")
        if os.path.exists(p):
            return p
    p = os.path.join(REFS, f"{handle}_og.png")
    return p if os.path.exists(p) else None


def build_one(entry, force=False):
    from PIL import Image

    slug, handle = entry["slug"], entry["handle"]
    out = os.path.join(HERE, "play", "ui", slug)
    os.makedirs(out, exist_ok=True)
    osbui = os.path.join(out, f"{slug}.osbui")
    if os.path.exists(osbui) and not force:
        print(f"skip {slug} (exists, --force to redo)")
        return slug

    src = ref_for(handle)
    if not src:
        raise RuntimeError(f"no ref art for {handle} (run fetch_backyard_roster.py)")
    im = Image.open(src).convert("RGB")
    side = min(im.size)
    im = im.crop(((im.width - side) // 2, (im.height - side) // 2,
                  (im.width + side) // 2, (im.height + side) // 2))
    im = im.resize((512, 512), Image.LANCZOS)
    portrait = os.path.join(out, "portrait_raw.png")
    im.save(portrait)

    # derivatives the site grid draws (90x86 tile, 256 thumb)
    sh([sys.executable, os.path.join(PIPE, "portrait_tiles.py"), out])

    # emblem: bold initial on flat magenta, stencil-derived by gen_ui_assets
    sys.path.insert(0, PIPE)
    from pixel_font import GLYPHS
    letter = (entry.get("short") or entry["display"])[:1].upper()
    glyph = GLYPHS.get(letter, GLYPHS["X"])
    gw, gh = len(glyph[0]), len(glyph)
    scale = 22
    ink = Image.new("RGBA", (gw * scale, gh * scale), (255, 0, 255, 255))
    px = ink.load()
    for y, row in enumerate(glyph):
        for x, ch in enumerate(row):
            if ch == "#":
                for dy in range(scale):
                    for dx in range(scale):
                        px[x * scale + dx, y * scale + dy] = (255, 255, 255, 255)
    canvas = Image.new("RGBA", (512, 512), (255, 0, 255, 255))
    canvas.alpha_composite(ink, ((512 - ink.width) // 2, (512 - ink.height) // 2 - 20))
    # hard 2-color posterize: keeps the stencil clustering exact and the
    # 8x10 stock downsample free of blur speckles (vanilla icons are flat).
    # NOTE: magenta (255,0,255) averages 170, so luminance thresholds eat
    # the bg — map on whiteness instead.
    px = canvas.load()
    for y in range(canvas.height):
        for x in range(canvas.width):
            r, g, b, a = px[x, y]
            px[x, y] = (255, 255, 255, 255) if min(r, g, b) > 200 else (255, 0, 255, 255)
    emblem_raw = os.path.join(out, "emblem_raw.png")
    canvas.save(emblem_raw)

    sh([sys.executable, os.path.join(PIPE, "gen_ui_assets.py"), osbui,
        "--art", portrait, "--stock-art", src, "--emblem", emblem_raw,
        "--name", entry["short"][:10],
        "--preview", os.path.join(out, "preview.png")])
    print(f"packed {slug} <- {handle} ({entry['base']})")
    return slug


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", help="only this starter slug")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    entries = json.load(open(CONFIG))
    if args.slug:
        entries = [e for e in entries if e["slug"] == args.slug]
        if not entries:
            sys.exit(f"unknown slug {args.slug}")
    done = [build_one(e, force=args.force) for e in entries]
    print(f"\n{len(done)} sprite packs. Missing for a full fighter: .osb6 (Tripo mesh + "
          "engine convert, needs keys/ROM) + announcer.wav (Fal).")


if __name__ == "__main__":
    main()
