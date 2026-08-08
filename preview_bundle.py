#!/usr/bin/env python3
"""Software-render a converted character bundle assembled on a SKELDUMP
skeleton — a converter sanity check before the in-game loader exists.

Orthographic front view, painter's algorithm, flat-shaded triangles using
mean vertex color, tinted by a simple headlight for depth cues.

Usage: preview_bundle.py bundle.json skeldump.txt out.png
"""
import json
import re
import sys

from PIL import Image, ImageDraw


def load_skeleton(path):
    joints = {}
    pat = re.compile(r"SKELDUMP: joint=(\d+) parent=(-?\d+) world=\(([^)]+)\)")
    for line in open(path):
        m = pat.search(line)
        if m:
            joints[int(m.group(1))] = [float(x) for x in m.group(3).split(",")]
    return joints


def main():
    bundle = json.load(open(sys.argv[1]))
    joints = load_skeleton(sys.argv[2])
    out_path = sys.argv[3]

    tris = []  # (depth, screen_pts, color)
    for part in bundle["parts"]:
        jw = joints.get(part["joint"])
        if jw is None:
            continue
        verts = [(v[0] + jw[0], v[1] + jw[1], v[2] + jw[2], v[3], v[4], v[5])
                 for v in part["verts"]]
        for a, b, c in part["tris"]:
            va, vb, vc = verts[a], verts[b], verts[c]
            # normal z for a cheap headlight
            ux, uy, uz = vb[0]-va[0], vb[1]-va[1], vb[2]-va[2]
            wx, wy, wz = vc[0]-va[0], vc[1]-va[1], vc[2]-va[2]
            nz = ux*wy - uy*wx
            nlen = max(1e-6, (ux*wy-uy*wx)**2 + (uy*wz-uz*wy)**2 + (uz*wx-ux*wz)**2) ** 0.5
            shade = 0.55 + 0.45 * max(0.0, nz / nlen)
            r = int(sum(v[3] for v in (va, vb, vc)) / 3 * shade)
            g = int(sum(v[4] for v in (va, vb, vc)) / 3 * shade)
            bcol = int(sum(v[5] for v in (va, vb, vc)) / 3 * shade)
            depth = (va[2] + vb[2] + vc[2]) / 3
            tris.append((depth, [(va[0], va[1]), (vb[0], vb[1]), (vc[0], vc[1])],
                         (min(255, r), min(255, g), min(255, bcol))))

    xs = [p[0] for _, pts, _ in tris for p in pts]
    ys = [p[1] for _, pts, _ in tris for p in pts]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    W = 700
    scale = (W - 80) / max(xmax - xmin, ymax - ymin)
    H = int((ymax - ymin) * scale) + 80

    def to_screen(p):
        return (40 + (p[0] - xmin) * scale, H - 40 - (p[1] - ymin) * scale)

    img = Image.new("RGB", (W, H), (30, 30, 40))
    draw = ImageDraw.Draw(img)
    for _, pts, col in sorted(tris, key=lambda t: t[0]):  # back to front
        draw.polygon([to_screen(p) for p in pts], fill=col)

    img.save(out_path)
    print(f"rendered {len(tris)} tris -> {out_path} ({W}x{H})")


if __name__ == "__main__":
    main()
