#!/usr/bin/env python3
"""Render a rigged GLB's bind pose (T-pose) outside the engine.

Per-pixel textured software rasterizer with a z-buffer — front,
three-quarter, side and back views on one sheet. Used to isolate
meshification defects from in-game conversion defects.

Usage: render_tpose.py rigged.glb out.png [--atlas atlas.png]
"""
import math
import sys

import numpy as np
from PIL import Image, ImageDraw

import convert_rigged as cr


def render(P, UV, T, N, atlas, view, S=760):
    AH, AW = atlas.shape[:2]
    span = (P.max(0) - P.min(0)).max()
    light = np.array([0.35, 0.75, 0.55], np.float32)
    light /= np.linalg.norm(light)
    Pc = P @ view.T
    x = (Pc[:, 0] - Pc[:, 0].mean()) / span * 640 + S / 2
    y = S / 2 - (Pc[:, 1] - Pc[:, 1].mean()) / span * 640
    z = Pc[:, 2]
    Nc = (N @ view.T) if N is not None else None
    imgbuf = np.full((S, S, 3), 40, np.float32)
    zbuf = np.full((S, S), -1e9, np.float32)
    for t in T:
        i, j, k = t
        xs = np.array([x[i], x[j], x[k]]); ys = np.array([y[i], y[j], y[k]])
        x0, x1 = int(max(0, xs.min())), int(min(S - 1, xs.max())) + 1
        y0, y1 = int(max(0, ys.min())), int(min(S - 1, ys.max())) + 1
        if x0 >= x1 or y0 >= y1:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        d = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0])
        if abs(d) < 1e-9:
            continue
        w0 = ((xs[1] - gx) * (ys[2] - gy) - (xs[2] - gx) * (ys[1] - gy)) / d
        w1 = ((xs[2] - gx) * (ys[0] - gy) - (xs[0] - gx) * (ys[2] - gy)) / d
        w2 = 1 - w0 - w1
        m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not m.any():
            continue
        zz = w0 * z[i] + w1 * z[j] + w2 * z[k]
        uu = w0 * UV[i, 0] + w1 * UV[j, 0] + w2 * UV[k, 0]
        vv = w0 * UV[i, 1] + w1 * UV[j, 1] + w2 * UV[k, 1]
        tx = np.clip((uu * AW).astype(int), 0, AW - 1)
        ty = np.clip((vv * AH).astype(int), 0, AH - 1)
        col = atlas[ty, tx]
        if Nc is not None:
            nn = w0[..., None] * Nc[i] + w1[..., None] * Nc[j] + w2[..., None] * Nc[k]
            l = np.clip((nn @ light) / (np.linalg.norm(nn, axis=-1) + 1e-9), 0, 1) * 0.45 + 0.62
            col = col * l[..., None]
        sub = m & (zz > zbuf[y0:y1, x0:x1])
        zbuf[y0:y1, x0:x1][sub] = zz[sub]
        imgbuf[y0:y1, x0:x1][sub] = np.clip(col[sub], 0, 255)
    return Image.fromarray(imgbuf.astype(np.uint8))


def main():
    glb, out = sys.argv[1], sys.argv[2]
    atlas_path = sys.argv[sys.argv.index("--atlas") + 1] if "--atlas" in sys.argv else None
    pos, nrm, uv, tris, img, jix, wts, names, jpos = cr.load_rigged(glb)
    P = np.array(pos, np.float32); UV = np.array(uv, np.float32)
    N = np.array(nrm, np.float32) if nrm is not None else None
    atlas = np.asarray((Image.open(atlas_path) if atlas_path else img).convert("RGB"), np.float32)

    def roty(a):
        c, s = math.cos(a), math.sin(a)
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], np.float32)

    # facing: use the converter's toe heuristic result implicitly — the
    # model faces +x or -x; pick the yaw where the nose (front) shows.
    S = 760
    views = [("front", roty(-math.pi / 2)), ("three-quarter", roty(-math.pi / 4)),
             ("side", np.eye(3, dtype=np.float32)), ("back", roty(math.pi / 2))]
    sheet = Image.new("RGB", (S * 4 + 50, S + 40), (20, 20, 24))
    dd = ImageDraw.Draw(sheet)
    for c, (lab, V) in enumerate(views):
        sheet.paste(render(P, UV, np.array(tris), N, atlas, V, S), (10 + c * (S + 10), 30))
        dd.text((10 + c * (S + 10) + S // 2 - 30, 10), lab, fill=(255, 255, 120))
    sheet.save(out)
    print(f"rendered {glb} -> {out}")


if __name__ == "__main__":
    main()
