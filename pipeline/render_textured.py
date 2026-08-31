#!/usr/bin/env python3
"""Faithful textured software render of a (possibly rigged) GLB: per-pixel
affine texture mapping, painter's algorithm, optional flat diffuse light.
Debug tool for bisecting where the pipeline loses visual quality.

Usage: render_textured.py model.glb out.png [--yaw DEG] [--size PX] [--unlit]
"""
import argparse
import io
import math
import sys

from PIL import Image

try:
    from .convert_glb import load_glb, read_accessor
except ImportError:  # direct execution: python3 pipeline/render_textured.py
    from convert_glb import load_glb, read_accessor


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("glb")
    ap.add_argument("out")
    ap.add_argument("--yaw", type=float, default=0.0)
    ap.add_argument("--pitch", type=float, default=0.0,
                    help="camera pitch in degrees (90 = top-down)")
    ap.add_argument("--size", type=int, default=900)
    ap.add_argument("--unlit", action="store_true")
    args = ap.parse_args()

    gltf, bin_ = load_glb(args.glb)
    prim = gltf["meshes"][0]["primitives"][0]
    pos = read_accessor(gltf, bin_, prim["attributes"]["POSITION"])
    uv = read_accessor(gltf, bin_, prim["attributes"]["TEXCOORD_0"])
    idx = [t[0] for t in read_accessor(gltf, bin_, prim["indices"])]
    tris = [(idx[i], idx[i+1], idx[i+2]) for i in range(0, len(idx), 3)]
    # resolve the material's baseColor image (images[0] can be a normal map)
    img_i = 0
    mat_i = prim.get("material")
    if mat_i is not None:
        bct = gltf["materials"][mat_i].get(
            "pbrMetallicRoughness", {}).get("baseColorTexture")
        if bct is not None:
            img_i = gltf["textures"][bct["index"]]["source"]
    bv = gltf["bufferViews"][gltf["images"][img_i]["bufferView"]]
    tex = Image.open(io.BytesIO(
        bin_[bv.get("byteOffset", 0):bv.get("byteOffset", 0)+bv["byteLength"]])).convert("RGB")
    TW, TH = tex.size

    W = H = args.size
    yaw = math.radians(args.yaw)
    cs, sn = math.cos(yaw), math.sin(yaw)
    pit = math.radians(args.pitch)
    cp, sp = math.cos(pit), math.sin(pit)

    def rot(v):
        x = v[0]*cs + v[2]*sn
        z = -v[0]*sn + v[2]*cs
        y = v[1]*cp - z*sp
        z = v[1]*sp + z*cp
        return (x, y, z)

    rpos = [rot(v) for v in pos]
    xs = [v[0] for v in rpos]
    ys = [v[1] for v in rpos]
    xc, yc = (min(xs)+max(xs))/2, (min(ys)+max(ys))/2
    ext = max(max(xs)-min(xs), max(ys)-min(ys)) or 1e-9
    sc = (H-80)/ext

    def proj(v):
        return (W/2 + (v[0]-xc)*sc, H/2 - (v[1]-yc)*sc, v[2])

    # light: fixed key from camera-up-left
    L = (-0.35, 0.5, 0.79)

    order = []
    for t in tris:
        s = [proj(rpos[i]) for i in t]
        order.append((sum(p[2] for p in s)/3, t, s))
    order.sort(key=lambda x: x[0])

    img = Image.new("RGB", (W, H), (255, 255, 255))
    for _, t, s in order:
        # camera-space normal for lighting (rpos is already rotated)
        a, b, c = (rpos[t[0]], rpos[t[1]], rpos[t[2]])
        u = [b[k]-a[k] for k in range(3)]
        w = [c[k]-a[k] for k in range(3)]
        n = [u[1]*w[2]-u[2]*w[1], u[2]*w[0]-u[0]*w[2], u[0]*w[1]-u[1]*w[0]]
        nlen = math.sqrt(n[0]*n[0]+n[1]*n[1]+n[2]*n[2]) or 1e-9
        shade = 1.0 if args.unlit else min(1.0, 0.45 + 0.55*max(
            0.0, (n[0]*L[0]+n[1]*L[1]+n[2]*L[2])/nlen))

        # affine map: texture tri -> screen tri
        x0, y0 = s[0][0], s[0][1]
        x1, y1 = s[1][0], s[1][1]
        x2, y2 = s[2][0], s[2][1]
        u0, v0 = uv[t[0]][0]*TW, uv[t[0]][1]*TH
        u1, v1 = uv[t[1]][0]*TW, uv[t[1]][1]*TH
        u2, v2 = uv[t[2]][0]*TW, uv[t[2]][1]*TH
        det = (x1-x0)*(y2-y0)-(x2-x0)*(y1-y0)
        if abs(det) < 1e-3:
            continue
        # solve inverse: screen -> texture
        A = ((u1-u0)*(y2-y0)-(u2-u0)*(y1-y0))/det
        B = ((u2-u0)*(x1-x0)-(u1-u0)*(x2-x0))/det
        C = u0 - A*x0 - B*y0
        D = ((v1-v0)*(y2-y0)-(v2-v0)*(y1-y0))/det
        E = ((v2-v0)*(x1-x0)-(v1-v0)*(x2-x0))/det
        F = v0 - D*x0 - E*y0

        xs = [x0, x1, x2]; ys2 = [y0, y1, y2]
        bx0, bx1 = max(0, int(min(xs))), min(W-1, int(max(xs))+1)
        by0, by1 = max(0, int(min(ys2))), min(H-1, int(max(ys2))+1)
        if bx1 <= bx0 or by1 <= by0:
            continue
        bw, bh = bx1-bx0+1, by1-by0+1
        patch = tex.transform((bw, bh), Image.AFFINE,
                              (A, B, C + A*bx0 + B*by0,
                               D, E, F + D*bx0 + E*by0),
                              resample=Image.BILINEAR)
        if shade < 0.999:
            patch = patch.point(lambda p, sh=shade: int(p*sh))
        mask = Image.new("L", (bw, bh), 0)
        from PIL import ImageDraw
        ImageDraw.Draw(mask).polygon(
            [(x0-bx0, y0-by0), (x1-bx0, y1-by0), (x2-bx0, y2-by0)], fill=255)
        img.paste(patch, (bx0, by0), mask)

    img.save(args.out)
    print(f"textured render {len(tris)} tris -> {args.out}")


if __name__ == "__main__":
    main()
