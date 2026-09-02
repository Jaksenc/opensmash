#!/usr/bin/env python3
"""portrait_tiles.py — small portrait derivatives for the site.

The site's roster grid draws each fighter in a 45x43 tile and the /create
page shows ~120px thumbnails, yet both were loading the 1024x1024
portrait_raw.png (~1.1 MB each): 28 MB for a 25-fighter home page. This
writes, next to portrait_raw.png:

  portrait_tile.png    90x86   (2x the grid cell; same centre-crop the grid
                                used to do in the browser, LANCZOS)
  portrait_medium.png  256x256 (thumbnails, previews)

Both are lossless PNG so the grid's pixel treatment is unchanged; the only
difference from the browser path is where the downscale happens.

Usage:
  portrait_tiles.py play/ui/<slug>            # one character
  portrait_tiles.py --all                      # every play/ui/*/portrait_raw.png
"""
import argparse
import glob
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TILE_W, TILE_H = 90, 86          # 2x CELL_W x CELL_H in visual/grid-replica.js
MEDIUM = 256


def centre_crop(image, aspect):
    w, h = image.size
    if w / h > aspect:
        cw = int(round(h * aspect))
        return image.crop(((w - cw) // 2, 0, (w - cw) // 2 + cw, h))
    ch = int(round(w / aspect))
    return image.crop((0, (h - ch) // 2, w, (h - ch) // 2 + ch))


def write_derivatives(ui_root, force=False):
    source = os.path.join(ui_root, "portrait_raw.png")
    if not os.path.isfile(source):
        raise FileNotFoundError(source)
    tile = os.path.join(ui_root, "portrait_tile.png")
    medium = os.path.join(ui_root, "portrait_medium.png")
    fresh = (os.path.isfile(tile) and os.path.isfile(medium) and
             os.path.getmtime(tile) >= os.path.getmtime(source) and
             os.path.getmtime(medium) >= os.path.getmtime(source))
    if fresh and not force:
        return False
    art = Image.open(source).convert("RGBA")
    centre_crop(art, TILE_W / TILE_H).resize((TILE_W, TILE_H), Image.LANCZOS).save(tile, optimize=True)
    centre_crop(art, 1.0).resize((MEDIUM, MEDIUM), Image.LANCZOS).save(medium, optimize=True)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ui_roots", nargs="*", help="play/ui/<slug> directories")
    ap.add_argument("--all", action="store_true", help="every play/ui/*/ with a portrait_raw.png")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    roots = list(a.ui_roots)
    if a.all:
        roots += sorted(os.path.dirname(p) for p in glob.glob(os.path.join(HERE, "play", "ui", "*", "portrait_raw.png")))
    if not roots:
        ap.error("give play/ui/<slug> directories or --all")
    written = 0
    for root in roots:
        if write_derivatives(root, a.force):
            written += 1
            t = os.path.getsize(os.path.join(root, "portrait_tile.png"))
            m = os.path.getsize(os.path.join(root, "portrait_medium.png"))
            print(f"{os.path.basename(root)}: tile {t / 1024:.1f} KB, medium {m / 1024:.0f} KB")
    print(f"{written} of {len(roots)} updated")


if __name__ == "__main__":
    sys.exit(main())
