#!/usr/bin/env python3
"""Texture-check contact sheet for a generated character: where do texture
artifacts enter the pipeline?

2x4 grid, all in T-pose so panels are directly comparable:

  [source image]    [GLB unlit front] [GLB unlit rear] [GLB unlit top]
  [GLB flat-shaded] [game unlit front] [game unlit rear] [game unlit top]

Column 1 (separated by a rule) is reference material: the gpt-image-2
source and a shaded view of the meshified GLB. Columns 2-4 pair the
rigged GLB's own texture (top row) against the converted bundle exactly
as the in-game OSB5 loader draws it (bottom row, preview_bundle --tpose).
A defect present on the bottom row but not the top entered during
conversion; present on both, it came from meshification or the source.

Usage: texture_check.py play/ui/<slug> [out.png] [--size PX]
Needs tpose.png, rigged.glb, and bundle.json in the character dir.
"""
import argparse
import glob
import json
import math
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))

# camera angles: front / rear / top-down (yaw, pitch)
VIEWS = [("front", -90, 0), ("rear", 90, 0), ("top", -90, 90)]


def mario_ghost(yaw, pitch, size):
    """Grey proportions ghost of vanilla Mario in the same synthesized
    T-pose: per-part convex hulls of the vanilla part dump, posed with
    constructed frames (vanilla limb geometry runs along local +x)."""
    import numpy as np
    from scipy.spatial import ConvexHull
    from preview_bundle import load_skeleton

    parts = {int(k): np.array(v, float) for k, v in
             json.load(open(os.path.join(HERE, "vanilla-mario-parts.json"))).items()}
    skel = load_skeleton(os.path.join(HERE, "mario.skel"))
    O = {j: np.array(o, float) for j, (o, _) in skel.items()}

    def frame_from_x(t, up_hint):
        # orthonormal row basis (row-vector convention) with local +x -> t
        t = np.array(t, float); t /= np.linalg.norm(t)
        u = np.array(up_hint, float)
        u = u - (u @ t) * t
        u /= np.linalg.norm(u)
        return np.stack([t, u, np.cross(t, u)])

    o6 = O[6]
    frames = {6: (o6, np.eye(3)), 12: (o6 + np.array([0.0, np.linalg.norm(O[12]-o6), 0.0]), np.eye(3))}
    fwd = np.array([1.0, 0.0, 0.0])
    for chain, side in (((8, 9, 10), -1.0), ((14, 15, 16), 1.0),
                        ((19, 20, 22), -1.0), ((24, 25, 27), 1.0)):
        j0, j1, j2 = chain
        arm = j0 in (8, 14)
        t = np.array((0.0, 0.0, side) if arm else (0.0, -1.0, 0.15*side))
        t /= np.linalg.norm(t)
        up = (0.0, 1.0, 0.0) if arm else (1.0, 0.0, 0.0)
        R = frame_from_x(t, up)
        off = O[j0] - o6
        o0 = o6 + np.array([0.0, off[1], side*math.hypot(off[0], off[2])])
        o1 = o0 + np.linalg.norm(O[j1]-O[j0])*t
        o2 = o1 + np.linalg.norm(O[j2]-O[j1])*t
        # feet keep their toe axis (local +x) pointing forward, not down
        R2 = frame_from_x(fwd, (0.0, 1.0, 0.0)) if not arm else R
        frames[j0], frames[j1], frames[j2] = (o0, R), (o1, R), (o2, R2)

    world, tris = [], []
    for j, verts in parts.items():
        if j not in frames or len(verts) < 4:
            continue
        o, R = frames[j]
        base = len(world)
        world.extend(v @ R + o for v in verts)
        try:
            for s in ConvexHull(verts).simplices:
                tris.append((base + s[0], base + s[1], base + s[2]))
        except Exception:
            continue

    ya, pi = math.radians(yaw), math.radians(pitch)
    cs, sn, cp, sp = math.cos(ya), math.sin(ya), math.cos(pi), math.sin(pi)

    def rot(v):
        x = v[0]*cs + v[2]*sn
        z = -v[0]*sn + v[2]*cs
        return np.array([x, v[1]*cp - z*sp, v[1]*sp + z*cp])

    rpos = [rot(v) for v in world]
    xs = [v[0] for v in rpos]; ys = [v[1] for v in rpos]
    xc, yc = (min(xs)+max(xs))/2, (min(ys)+max(ys))/2
    sc = (size-80)/(max(max(xs)-min(xs), max(ys)-min(ys)) or 1e-9)
    L = np.array([-0.35, 0.5, 0.79])
    img = Image.new("RGB", (size, size), (29, 29, 40))
    dr = ImageDraw.Draw(img)
    order = []
    for t3 in tris:
        s = [(size/2 + (rpos[i][0]-xc)*sc, size/2 - (rpos[i][1]-yc)*sc,
              rpos[i][2]) for i in t3]
        order.append((sum(p[2] for p in s)/3, t3, s))
    order.sort(key=lambda x: x[0])
    for _, t3, s in order:
        a, b, c = (rpos[i] for i in t3)
        n = np.cross(b-a, c-a)
        nl = np.linalg.norm(n) or 1e-9
        # ConvexHull winding is arbitrary — light by absolute incidence
        g = int(150 * min(1.0, 0.45 + 0.55*abs(float(n @ L))/nl)) + 40
        dr.polygon([(p[0], p[1]) for p in s], fill=(g, g, g+8))
    return img


def vanilla_idle_capture():
    """Newest cached vanilla Mario pose-capture idle frame, cropped."""
    import numpy as np
    cells = sorted(glob.glob(os.path.join(HERE, "eval/cells/pose-vanilla-fk0-*/frame_800.png")),
                   key=os.path.getmtime)
    if not cells:
        return None
    im = Image.open(cells[-1]).convert("RGB")
    a = np.asarray(im).astype(int)
    mask = np.abs(a - a[5, 5]).sum(axis=2) > 40
    ys, xs = np.where(mask)
    if not len(xs):
        return im
    p = 30
    return im.crop((max(xs.min()-p, 0), max(ys.min()-p, 0),
                    min(xs.max()+p, im.width), min(ys.max()+p, im.height)))


def run(script, src, out, yaw, pitch, unlit, extra=()):
    cmd = [sys.executable, os.path.join(HERE, script), src, out,
           "--yaw", str(yaw), "--pitch", str(pitch), *extra]
    if unlit:
        cmd.append("--unlit")
    subprocess.run(cmd, check=True, cwd=HERE, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chardir", help="character dir (play/ui/<slug>)")
    ap.add_argument("out", nargs="?", default=None)
    ap.add_argument("--size", type=int, default=700, help="panel height px")
    args = ap.parse_args()

    d = args.chardir.rstrip("/")
    slug = os.path.basename(d)
    out_path = args.out or os.path.join(d, "texture_check.png")
    tpose = os.path.join(d, "tpose.png")
    glb = os.path.join(d, "rigged.glb")
    bundle = os.path.join(d, "bundle.json")
    for p in (tpose, glb, bundle):
        if not os.path.exists(p):
            sys.exit(f"missing {p}")

    tmp = tempfile.mkdtemp(prefix="texcheck-")
    cells = {}
    for name, yaw, pitch in VIEWS:
        p = os.path.join(tmp, f"glb-{name}.png")
        run("render_textured.py", glb, p, yaw, pitch, unlit=True)
        cells[("glb", name)] = p
        p = os.path.join(tmp, f"game-{name}.png")
        run("preview_bundle.py", bundle, p, yaw, pitch, unlit=True,
            extra=("--tpose",))
        cells[("game", name)] = p
    shaded = os.path.join(tmp, "glb-shaded.png")
    run("render_textured.py", glb, shaded, -90, 0, unlit=False)

    H = args.size
    def fit(path):
        im = Image.open(path).convert("RGB")
        return im.resize((int(im.width * H / im.height), H), Image.LANCZOS)

    grid = [
        [(fit(tpose), "source image (gpt-image-2)")]
        + [(fit(cells[("glb", n)]), f"meshified GLB, unlit - {n}")
           for n, _, _ in VIEWS],
        [(fit(shaded), "meshified GLB, flat-shaded")]
        + [(fit(cells[("game", n)]), f"in-game texture (OSB5), unlit - {n}")
           for n, _, _ in VIEWS],
    ]
    # row 3: vanilla Mario — the conform target's true proportions
    def fit_im(im):
        return im.resize((int(im.width * H / im.height), H), Image.LANCZOS)
    idle = vanilla_idle_capture()
    ref = (fit_im(idle), "vanilla Mario, in-engine idle") if idle else \
          (Image.new("RGB", (H, H), (24, 24, 30)), "no vanilla capture cached")
    grid.append([ref] + [(fit_im(mario_ghost(yaw, pitch, 900)),
                          f"vanilla Mario proportions - {n}")
                         for n, yaw, pitch in VIEWS])

    PAD, LBL = 30, 42
    rows = len(grid)
    col_w = [max(grid[r][c][0].width for r in range(rows)) for c in range(4)]
    W = sum(col_w) + PAD * 5 + PAD          # extra PAD around the rule
    row_h = LBL + H
    out = Image.new("RGB", (W, PAD + rows * (row_h + PAD)), (24, 24, 30))
    dr = ImageDraw.Draw(out)
    for r, row in enumerate(grid):
        y = PAD + r * (row_h + PAD)
        x = PAD
        for c, (im, label) in enumerate(row):
            cx = x + (col_w[c] - im.width) // 2
            dr.text((x, y + 8), label, fill=(235, 235, 235))
            out.paste(im, (cx, y + LBL))
            x += col_w[c] + PAD
            if c == 0:
                x += PAD           # room for the separator rule
    rx = PAD + col_w[0] + PAD
    dr.line([(rx + PAD // 2, PAD), (rx + PAD // 2, out.height - PAD)],
            fill=(90, 90, 110), width=3)
    dr.text((PAD, out.height - PAD + 6), slug, fill=(160, 160, 180))
    out.save(out_path)
    print(f"texture check -> {out_path}")


if __name__ == "__main__":
    main()
