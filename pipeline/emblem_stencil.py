#!/usr/bin/env python3
"""Turn flat-colour emblem art into a vanilla-style stencil mask.

The engine draws a series emblem as a single flat tint: the .osbui emblem
canvas is pure coverage, and ftport's port_ui_write_canvas_fit thresholds
it to one intensity. So ONLY the mask shape survives — taking the art's
alpha channel (its outer silhouette) throws away everything that made the
art readable and every solid object lands as a blob.

Look at web-prototype/visual/assets/ui_refs/emblem_ref.png (the game's own ten emblems, dumped by
extract_vanilla_emblems.py): every one is a stencil. The Poke Ball is a
plain circle that reads only because its band and centre are cut through;
Yoshi's egg is an oval with its spots punched out; the Triforce is hollow.
Interior negative space, not outline detail, is what carries the glyph.

So: cluster the art's flat colours, then 2-colour the palette so adjacent
colour regions alternate ink/hole, seeded with the largest region as ink
(the body stays solid) and the darkest as ink (outline strokes are ink,
like the art's own linework). The outer rim is forced to ink so cuts read
as holes in a shape rather than as a fragmented silhouette.

  emblem_stencil.py art.png [--out mask.png] [--preview p.png] [--json]
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

WORK = 128          # working resolution (long edge) for clustering
RIM = 2             # forced-ink border, in working pixels
CRUMB = 0.010       # drop ink islands below this fraction of the silhouette
SPECK = 0.006       # fill holes below this fraction of the silhouette


def key_bg(im, thresh=90):
    """Alpha-key the flat generated background, matching gen_ui_assets."""
    a = np.asarray(im.convert("RGB"), np.int16)
    return np.abs(a - a[2, 2]).sum(2) > thresh


def _cluster(rgb, inside, k):
    """k-means the interior's flat colours -> (label map, centres)."""
    import cv2
    px = rgb[inside].astype(np.float32)
    k = min(k, len(np.unique(px, axis=0)))
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, lab, cen = cv2.kmeans(px, k, None, crit, 4, cv2.KMEANS_PP_CENTERS)
    L = np.full(inside.shape, -1, np.int32)
    L[inside] = lab.ravel()
    return L, cen


def _adjacency(L, n):
    """How many pixels each pair of colour clusters touches along."""
    A = np.zeros((n, n), np.int64)
    for dy, dx in ((0, 1), (1, 0)):
        a, b = L[:L.shape[0] - dy, :L.shape[1] - dx], L[dy:, dx:]
        m = (a >= 0) & (b >= 0) & (a != b)
        np.add.at(A, (a[m], b[m]), 1)
        np.add.at(A, (b[m], a[m]), 1)
    return A


def stencil(art, work=WORK, rim=RIM, k=5):
    """art (path or PIL image) -> (ink mask, silhouette) as bool arrays."""
    im = art if isinstance(art, Image.Image) else Image.open(art)
    im = im.convert("RGBA")
    ys, xs = np.where(key_bg(im))
    if not len(xs):
        return None, None
    im = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    s = work / max(im.size)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))),
                   Image.LANCZOS)

    drawn = ndi.binary_closing(key_bg(im), np.ones((3, 3)))
    sil = ndi.binary_fill_holes(drawn)          # outer silhouette
    if not drawn.any():
        return None, None
    L, cen = _cluster(np.asarray(im.convert("RGB"), np.uint8), drawn, k)
    n = len(cen)
    area = np.array([(L == i).sum() for i in range(n)], np.int64)
    lum = cen @ np.array([0.299, 0.587, 0.114], np.float32)
    A = _adjacency(L, n)

    # 2-colour the palette graph: body is ink, its neighbours alternate.
    ink = {int(np.argmax(area)): True, int(np.argmin(lum)): True}
    for c in np.argsort(-area):
        c = int(c)
        if c not in ink:
            ink[c] = sum(A[c, d] * (1 if v else -1) for d, v in ink.items()) < 0
    m = np.zeros(L.shape, bool)
    for c, v in ink.items():
        if v:
            m |= (L == c)

    # keep the outer rim solid so cuts read as holes, not as a torn edge
    edge = sil & ~ndi.binary_erosion(sil, np.ones((2 * rim + 1,) * 2))
    m = (m & drawn) | edge
    # min feature size: no hairline ink, no hairline cuts
    m = ndi.binary_closing(ndi.binary_opening(m, np.ones((3, 3))), np.ones((3, 3)))
    m |= edge
    m &= sil

    lb, nl = ndi.label(m)                       # drop ink crumbs
    if nl:
        keep = 1 + np.where(ndi.sum(m, lb, range(1, nl + 1)) >= CRUMB * sil.sum())[0]
        m = np.isin(lb, keep)
    holes = sil & ~m
    hb, nh = ndi.label(holes)                   # fill speckle cuts
    if nh:
        fill = 1 + np.where(ndi.sum(holes, hb, range(1, nh + 1)) < SPECK * sil.sum())[0]
        m |= np.isin(hb, fill)
    return m, sil


def score(m, sil):
    """Legibility stats. A featureless blob has no cuts and a convex outline."""
    import cv2
    a = float(sil.sum()) or 1.0
    cnts, _ = cv2.findContours(sil.astype(np.uint8), cv2.RETR_EXTERNAL,
                               cv2.CHAIN_APPROX_SIMPLE)
    hull = max((cv2.contourArea(cv2.convexHull(c)) for c in cnts), default=a) or a
    holes = sil & ~m
    hb, nh = ndi.label(holes)
    big = int((ndi.sum(holes, hb, range(1, nh + 1)) >= 0.01 * a).sum()) if nh else 0
    st = {"ink_frac": round(m.sum() / a, 3),
          "cut_frac": round(holes.sum() / a, 3),
          "cuts": big,
          "hull_fill": round(a / hull, 3)}
    st["blobby"] = bool(st["cut_frac"] < 0.06 and st["hull_fill"] > 0.88)
    return st


def canvas(m, n=48):
    """Fit the mask's content bbox into an n*n coverage canvas (osbui form)."""
    im = Image.fromarray((m * 255).astype(np.uint8))
    im = im.crop(im.getbbox())
    s = min(n / im.width, n / im.height)
    g = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))),
                  Image.LANCZOS)
    cv = Image.new("L", (n, n), 0)
    cv.paste(g, ((n - g.width) // 2, (n - g.height) // 2))
    return cv


def _fit(cv, w, h):
    """Mimic ftport port_ui_write_canvas_fit for previews."""
    a = np.asarray(cv)
    ys, xs = np.where(a > 0)
    sub = cv.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    s = min(w / sub.width, h / sub.height)
    f = sub.resize((max(1, int(sub.width * s + .5)), max(1, int(sub.height * s + .5))),
                   Image.NEAREST)
    out = Image.new("L", (w, h), 0)
    out.paste(f, ((w - f.width) // 2, (h - f.height) // 2))
    return out.point(lambda v: 255 if v >= 128 else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("art")
    ap.add_argument("--out", default=None, help="write the mask as a PNG")
    ap.add_argument("--preview", default=None, help="art | mask | 64x48 | 32x24 sheet")
    ap.add_argument("--canvas", type=int, default=48)
    a = ap.parse_args()
    m, sil = stencil(a.art)
    if m is None:
        print(json.dumps({"error": "empty art"}))
        sys.exit(1)
    st = score(m, sil)
    if a.out:
        canvas(m, a.canvas).save(a.out)
    if a.preview:
        cv = canvas(m, a.canvas)
        tiles = [Image.open(a.art).convert("RGB"), cv.convert("RGB"),
                 _fit(cv, 64, 48).convert("RGB"), _fit(cv, 32, 24).convert("RGB")]
        c = 160
        sheet = Image.new("RGB", (c * len(tiles), c), (35, 35, 35))
        for i, t in enumerate(tiles):
            t = t.resize((c - 16, max(1, round((c - 16) * t.height / t.width))),
                         Image.NEAREST)
            sheet.paste(t, (i * c + 8, (c - t.height) // 2))
        sheet.save(a.preview)
    print(json.dumps(st))


if __name__ == "__main__":
    main()
