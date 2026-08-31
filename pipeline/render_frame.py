#!/usr/bin/env python3
"""Headless twin of viewer.html: render bundle posed by a dumped game frame
to a high-res PNG. My verification eyes for the mesh pipeline.

Usage:
  render_frame.py frames.json bundle.json out.png [--frame N] [--player P]
                  [--yaw DEG] [--size PX] [--wire] [--skel]
  --frame accepts comma list (renders a horizontal strip): --frame 0,40,80
"""
import argparse
import json
import math

from PIL import Image, ImageDraw


def xf(v, fr):
    R, o = fr["R"], fr["o"]
    return (v[0]*R[0][0] + v[1]*R[1][0] + v[2]*R[2][0] + o[0],
            v[0]*R[0][1] + v[1]*R[1][1] + v[2]*R[2][1] + o[1],
            v[0]*R[0][2] + v[1]*R[1][2] + v[2]*R[2][2] + o[2])


def render(frame, bundle, parents, args, W, H):
    img = Image.new("RGB", (W, H), (29, 29, 40))
    draw = ImageDraw.Draw(img)
    pf = frame["players"].get(str(args.player)) or frame["players"].get(args.player)
    if pf is None:
        draw.text((20, 20), "no player data", fill=(255, 80, 80))
        return img

    joints = pf["joints"]
    root = joints.get("0") or joints.get(0) or next(iter(joints.values()))
    cx, cy, cz = root["o"]
    yaw = math.radians(args.yaw)
    cs, sn = math.cos(yaw), math.sin(yaw)
    scale = args.size / 260.0 * (args.zoom / 100.0)

    def project(w):
        x = (w[0]-cx)*cs + (w[2]-cz)*sn
        z = -(w[0]-cx)*sn + (w[2]-cz)*cs
        y = w[1]-cy
        return (W/2 + x*scale, H*0.82 - y*scale, z)

    tris = []
    for part in bundle["parts"]:
        fr = joints.get(str(part["joint"])) or joints.get(part["joint"])
        if fr is None:
            continue
        world = [xf(v, fr) for v in part["verts"]]
        scr = [project(w) for w in world]
        for t in part["tris"]:
            a, b, c = scr[t[0]], scr[t[1]], scr[t[2]]
            ux, uy = b[0]-a[0], b[1]-a[1]
            wx, wy = c[0]-a[0], c[1]-a[1]
            nz = ux*wy - uy*wx
            la = math.hypot(ux, uy)*math.hypot(wx, wy) + 1e-6
            shade = 0.55 + 0.45*max(0.0, -nz/la)
            vr = sum(part["verts"][i][3] for i in t)/3
            vg = sum(part["verts"][i][4] for i in t)/3
            vb = sum(part["verts"][i][5] for i in t)/3
            col = (int(vr*shade), int(vg*shade), int(vb*shade))
            tris.append(((a[2]+b[2]+c[2])/3, (a[:2], b[:2], c[:2]), col))

    tris.sort(key=lambda x: x[0])
    for _, pts, col in tris:
        if args.wire:
            draw.polygon(list(pts), outline=col)
        else:
            draw.polygon(list(pts), fill=col)

    if args.skel:
        for j, fr in joints.items():
            p = project(fr["o"])
            pj = parents.get(str(j), parents.get(j, -1))
            pfr = joints.get(str(pj)) or joints.get(pj)
            if pfr:
                q = project(pfr["o"])
                draw.line([p[:2], q[:2]], fill=(120, 200, 255), width=2)
            draw.rectangle([p[0]-2, p[1]-2, p[0]+2, p[1]+2], fill=(255, 210, 74))
            draw.text((p[0]+4, p[1]-10), str(j), fill=(255, 210, 74))

    draw.text((10, 8), f"t={frame['t']} st={pf['st']} yaw={args.yaw}",
              fill=(160, 160, 200))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_json")
    ap.add_argument("bundle_json")
    ap.add_argument("out")
    ap.add_argument("--frame", default="0")
    ap.add_argument("--player", type=int, default=0)
    ap.add_argument("--yaw", type=float, default=0.0)
    ap.add_argument("--size", type=int, default=1100)
    ap.add_argument("--zoom", type=float, default=100.0)
    ap.add_argument("--wire", action="store_true")
    ap.add_argument("--skel", action="store_true")
    args = ap.parse_args()

    data = json.load(open(args.frames_json))
    bundle = json.load(open(args.bundle_json))
    idxs = [int(x) for x in args.frame.split(",")]
    W = H = args.size

    panels = [render(data["frames"][i], bundle, data["parents"], args, W, H)
              for i in idxs]
    strip = Image.new("RGB", (W*len(panels), H))
    for i, p in enumerate(panels):
        strip.paste(p, (i*W, 0))
    strip.save(args.out)
    print(f"rendered frames {idxs} -> {args.out}")


if __name__ == "__main__":
    main()
