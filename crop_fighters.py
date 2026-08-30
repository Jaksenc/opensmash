#!/usr/bin/env python3
"""Locate the two fighters in an eval screenshot and emit zoomed crops.

Fighters are the only Mario-palette blobs (strong red cap + cobalt overalls)
against the Hyrule stone/roof palette. Detects clusters of red|blue pixels,
merges nearby clusters, returns the two largest boxes (left fighter first).

Usage:
  crop_fighters.py shot.png out_prefix [--pad 90] [--h 480]
Emits out_prefix-L.png and out_prefix-R.png.
"""
import sys

import numpy as np
from PIL import Image


def fighter_boxes(img):
    a = np.asarray(img.convert("RGB"), dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    red = (r > 130) & (r - g > 60) & (r - b > 60)
    blue = (b > 90) & (b - r > 30) & (b - g > 20)
    mask = red | blue
    # kill HUD band (bottom 22%)
    mask[int(mask.shape[0] * 0.78):, :] = False

    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return []
    pts = np.stack([xs, ys], 1)
    # greedy cluster by x with generous gap
    order = np.argsort(pts[:, 0])
    pts = pts[order]
    clusters = []
    cur = [pts[0]]
    for p in pts[1:]:
        if p[0] - cur[-1][0] > img.width * 0.04:
            clusters.append(np.array(cur))
            cur = [p]
        else:
            cur.append(p)
    clusters.append(np.array(cur))
    boxes = []
    for c in clusters:
        if len(c) < 60:
            continue
        x0, y0 = c.min(0)
        x1, y1 = c.max(0)
        boxes.append((int(x0), int(y0), int(x1), int(y1), len(c)))
    boxes.sort(key=lambda bx: -bx[4])
    boxes = boxes[:2]
    boxes.sort(key=lambda bx: bx[0])
    return boxes


def crop(img, box, pad, out_h):
    x0, y0, x1, y1, _ = box
    x0 -= pad; y0 -= pad; x1 += pad; y1 += pad
    x0 = max(0, x0); y0 = max(0, y0)
    x1 = min(img.width, x1); y1 = min(img.height, y1)
    c = img.crop((x0, y0, x1, y1))
    w = int(c.width * out_h / c.height)
    return c.resize((w, out_h), Image.LANCZOS)


def main():
    path, prefix = sys.argv[1], sys.argv[2]
    pad = int(sys.argv[sys.argv.index("--pad") + 1]) if "--pad" in sys.argv else 90
    out_h = int(sys.argv[sys.argv.index("--h") + 1]) if "--h" in sys.argv else 480
    img = Image.open(path)
    boxes = fighter_boxes(img)
    names = ["L", "R"]
    for box, name in zip(boxes, names):
        crop(img, box, pad, out_h).save(f"{prefix}-{name}.png")
    print(f"{path}: {len(boxes)} fighters")


if __name__ == "__main__":
    main()
