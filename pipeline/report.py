#!/usr/bin/env python3
"""Character verification report: the reproducible QA loop for the mesh
pipeline. Renders the OSB3 bundle EXACTLY as the game does (atlas texture x
baked shade, posed by real dumped joint matrices) and computes defect
metrics, emitting one self-contained HTML page.

Usage:
  report.py bundle.json frames.json out.html
            [--frames 0,60,120,180,235] [--size 640]
            [--refs label=path.png ...]

Metrics:
  - holes: interior background pixels enclosed by the character silhouette
    (flood fill from image border; leftover background inside = holes)
  - seam divergence: duplicated boundary triangles (identical at rest)
    measured per frame for how far their copies pull apart
  - per-part table: verts/tris, cumulative joint rotation across the dump
    (a part whose joint travels but whose geometry shouldn't => binding bug)
"""
import argparse
import base64
import io
import json
import math
import os

from PIL import Image, ImageDraw


# ------------------------------------------------------------ pose + render
def pose_part(part, fr):
    R, o = fr["R"], fr["o"]
    out = []
    for v in part["verts"]:
        out.append((v[0]*R[0][0] + v[1]*R[1][0] + v[2]*R[2][0] + o[0],
                    v[0]*R[0][1] + v[1]*R[1][1] + v[2]*R[2][1] + o[1],
                    v[0]*R[0][2] + v[1]*R[1][2] + v[2]*R[2][2] + o[2]))
    return out


def render_frame_textured(bundle, atlas, frame, player, size, zoom):
    W = H = size
    pf = frame["players"].get(str(player)) or frame["players"].get(player)
    img = Image.new("RGB", (W, H), (29, 29, 40))
    if pf is None:
        return img, None
    joints = pf["joints"]
    root = joints.get("0") or next(iter(joints.values()))
    cx, cy, cz = root["o"]
    scale = size / 260.0 * (zoom / 100.0)
    TW, TH = atlas.size

    def project(w):
        return (W/2 + (w[0]-cx)*scale, H*0.82 - (w[1]-cy)*scale, w[2]-cz)

    order = []
    for part in bundle["parts"]:
        fr = joints.get(str(part["joint"])) or joints.get(part["joint"])
        if fr is None:
            continue
        world = pose_part(part, fr)
        scr = [project(w) for w in world]
        for t in part["tris"]:
            s = [scr[i] for i in t]
            depth = sum(p[2] for p in s)/3
            uvs = [(part["verts"][i][6]*TW, part["verts"][i][7]*TH) for i in t]
            shade = sum(part["verts"][i][8] for i in t)/(3*255.0)
            order.append((depth, s, uvs, shade))
    order.sort(key=lambda x: x[0])

    for _, s, uvs, shade in order:
        (x0, y0, _), (x1, y1, _), (x2, y2, _) = s
        (u0, v0), (u1, v1), (u2, v2) = uvs
        det = (x1-x0)*(y2-y0)-(x2-x0)*(y1-y0)
        if abs(det) < 1e-3:
            continue
        A = ((u1-u0)*(y2-y0)-(u2-u0)*(y1-y0))/det
        B = ((u2-u0)*(x1-x0)-(u1-u0)*(x2-x0))/det
        C = u0 - A*x0 - B*y0
        D = ((v1-v0)*(y2-y0)-(v2-v0)*(y1-y0))/det
        E = ((v2-v0)*(x1-x0)-(v1-v0)*(x2-x0))/det
        F = v0 - D*x0 - E*y0
        xs, ys = [x0, x1, x2], [y0, y1, y2]
        bx0, bx1 = max(0, int(min(xs))), min(W-1, int(max(xs))+1)
        by0, by1 = max(0, int(min(ys))), min(H-1, int(max(ys))+1)
        if bx1 <= bx0 or by1 <= by0:
            continue
        bw, bh = bx1-bx0+1, by1-by0+1
        patch = atlas.transform((bw, bh), Image.AFFINE,
                                (A, B, C + A*bx0 + B*by0,
                                 D, E, F + D*bx0 + E*by0),
                                resample=Image.BILINEAR)
        if shade < 0.999:
            patch = patch.point(lambda p, sh=shade: int(p*sh))
        mask = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(mask).polygon(
            [(x0-bx0, y0-by0), (x1-bx0, y1-by0), (x2-bx0, y2-by0)], fill=255)
        img.paste(patch, (bx0, by0), mask)
    return img, pf


# ------------------------------------------------------------------ metrics
def hole_metric(img, bg=(29, 29, 40)):
    """Seam holes: interior background enclosed by the silhouette, MINUS
    wide enclosed regions (space between limbs is legitimately enclosed —
    a stride pose encloses the crotch gap). A region counts as a seam
    hole only if it is thin: no pixel farther than 4px from geometry.
    Wide enclosed regions are tinted amber in the annotation, seam holes
    red."""
    W, H = img.size
    px = img.load()
    is_bg = [[px[x, y] == bg for x in range(W)] for y in range(H)]
    seen = [[False]*W for _ in range(H)]
    stack = ([(x, 0) for x in range(W)] + [(x, H-1) for x in range(W)]
             + [(0, y) for y in range(H)] + [(W-1, y) for y in range(H)])
    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= W or y >= H or seen[y][x] or not is_bg[y][x]:
            continue
        seen[y][x] = True
        stack.extend([(x+1, y), (x-1, y), (x, y+1), (x, y-1)])
    enclosed = [[is_bg[y][x] and not seen[y][x] for x in range(W)]
                for y in range(H)]

    # group enclosed pixels into regions; classify by max depth from edge
    lab = [[-1]*W for _ in range(H)]
    regions = []
    for y0 in range(H):
        for x0 in range(W):
            if not enclosed[y0][x0] or lab[y0][x0] >= 0:
                continue
            rid = len(regions)
            comp = []
            st = [(x0, y0)]
            lab[y0][x0] = rid
            while st:
                x, y = st.pop()
                comp.append((x, y))
                for nx, ny in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
                    if 0 <= nx < W and 0 <= ny < H and enclosed[ny][nx] \
                            and lab[ny][nx] < 0:
                        lab[ny][nx] = rid
                        st.append((nx, ny))
            regions.append(comp)

    def max_depth(comp):
        cs = set(comp)
        depth = {p: 0 for p in comp
                 if any(q not in cs for q in
                        ((p[0]+1, p[1]), (p[0]-1, p[1]),
                         (p[0], p[1]+1), (p[0], p[1]-1)))}
        frontier = list(depth)
        d = 0
        while frontier:
            d += 1
            nxt = []
            for (x, y) in frontier:
                for q in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
                    if q in cs and q not in depth:
                        depth[q] = d
                        nxt.append(q)
            frontier = nxt
        return d

    annotated = img.copy()
    ap = annotated.load()
    seam_px = 0
    for comp in regions:
        thin = max_depth(comp) <= 4
        for x, y in comp:
            ap[x, y] = (255, 40, 40) if thin else (200, 150, 40)
        if thin:
            seam_px += len(comp)
    return seam_px, annotated


def find_dups(bundle, frame0, player):
    pf = frame0["players"].get(str(player))
    posed = {}
    for pi, part in enumerate(bundle["parts"]):
        fr = pf["joints"].get(str(part["joint"]))
        posed[pi] = pose_part(part, fr) if fr else None
    key2copies = {}
    for pi, part in enumerate(bundle["parts"]):
        w = posed[pi]
        if not w:
            continue
        for ti, t in enumerate(part["tris"]):
            key = "|".join(sorted(",".join(str(round(c*4)) for c in w[i]) for i in t))
            key2copies.setdefault(key, []).append((pi, ti))
    return [v for v in key2copies.values() if len(v) > 1], posed


def divergence(bundle, frames, player, dups):
    worst = []
    for f in frames:
        pf = f["players"].get(str(player))
        if not pf:
            worst.append(0)
            continue
        posed = {}
        for pi, part in enumerate(bundle["parts"]):
            fr = pf["joints"].get(str(part["joint"]))
            posed[pi] = pose_part(part, fr) if fr else None
        wmax = 0.0
        for group in dups:
            (p0, t0) = group[0]
            if not posed[p0]:
                continue
            tri0 = [posed[p0][i] for i in bundle["parts"][p0]["tris"][t0]]
            for (pk, tk) in group[1:]:
                if not posed[pk]:
                    continue
                trik = [posed[pk][i] for i in bundle["parts"][pk]["tris"][tk]]
                for a in tri0:
                    d = min(math.dist(a, b) for b in trik)
                    if d > wmax:
                        wmax = d
        worst.append(round(wmax, 1))
    return worst


def part_travel(frames, player):
    travel = {}
    prev = {}
    for f in frames:
        pf = f["players"].get(str(player))
        if not pf:
            continue
        for j, fr in pf["joints"].items():
            b = fr["R"][0]
            if j in prev:
                a = prev[j]
                na = math.sqrt(sum(c*c for c in a)) or 1e-9
                nb = math.sqrt(sum(c*c for c in b)) or 1e-9
                dot = max(-1, min(1, sum(a[k]*b[k] for k in range(3))/(na*nb)))
                travel[j] = travel.get(j, 0.0) + math.degrees(math.acos(dot))
            prev[j] = b
    return travel


def b64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle_json")
    ap.add_argument("frames_json")
    ap.add_argument("out_html")
    ap.add_argument("--frames", default="0,60,120,180,235")
    ap.add_argument("--player", type=int, default=0)
    ap.add_argument("--size", type=int, default=640)
    ap.add_argument("--zoom", type=float, default=58)
    ap.add_argument("--refs", nargs="*", default=[])
    args = ap.parse_args()

    bundle = json.load(open(args.bundle_json))
    base = os.path.dirname(os.path.abspath(args.bundle_json))
    atlas = Image.open(os.path.join(base, bundle["atlas"])).convert("RGB")
    data = json.load(open(args.frames_json))
    frames = data["frames"]
    idxs = [int(x) for x in args.frames.split(",")]

    rows = []
    print(f"{'frame':>6} {'holes_px':>9} note")
    for i in idxs:
        img, pf = render_frame_textured(bundle, atlas, frames[i],
                                        args.player, args.size, args.zoom)
        nholes, annotated = hole_metric(img)
        rows.append((frames[i]["t"], pf["st"] if pf else "-", img, annotated, nholes))
        print(f"{frames[i]['t']:>6} {nholes:>9}")

    dups, _ = find_dups(bundle, frames[0], args.player)
    div = divergence(bundle, [frames[i] for i in idxs], args.player, dups)
    travel = part_travel(frames, args.player)
    print(f"dup tri groups: {len(dups)}; worst divergence per frame: {div}")

    html = ["<!doctype html><meta charset='utf-8'><title>bundle report</title>",
            "<style>body{background:#14141c;color:#cfcfe0;font:13px sans-serif;padding:14px}",
            "img{image-rendering:auto;border:1px solid #333;margin:3px}",
            "table{border-collapse:collapse;margin:10px 0}",
            "td,th{border:1px solid #444;padding:3px 9px}</style>",
            f"<h2>{os.path.basename(args.bundle_json)}</h2>"]

    if args.refs:
        html.append("<h3>references</h3>")
        for r in args.refs:
            label, path = r.split("=", 1)
            im = Image.open(path)
            im.thumbnail((args.size, args.size))
            html.append(f"<figure style='display:inline-block'><img src='{b64(im)}'>"
                        f"<figcaption>{label}</figcaption></figure>")

    html.append("<h3>posed textured renders (game-faithful) + hole overlay</h3>")
    for (t, st, img, annotated, nholes) in rows:
        html.append(f"<figure style='display:inline-block'><img src='{b64(img)}'>"
                    f"<figcaption>t={t} st={st}</figcaption></figure>")
        html.append(f"<figure style='display:inline-block'><img src='{b64(annotated)}'>"
                    f"<figcaption>holes: {nholes}px</figcaption></figure>")

    html.append("<h3>metrics</h3><table><tr><th>frame</th><th>holes px</th>"
                "<th>worst seam divergence (units)</th></tr>")
    for (t, st, _, _, nholes), dv in zip(rows, div):
        html.append(f"<tr><td>{t}</td><td>{nholes}</td><td>{dv}</td></tr>")
    html.append("</table>")

    html.append("<table><tr><th>part joint</th><th>verts</th><th>tris</th>"
                "<th>joint travel (deg over dump)</th></tr>")
    for p in bundle["parts"]:
        j = str(p["joint"])
        html.append(f"<tr><td>{j}</td><td>{len(p['verts'])}</td>"
                    f"<td>{len(p['tris'])}</td><td>{travel.get(j, 0):.0f}</td></tr>")
    html.append("</table>")
    html.append(f"<p>duplicated boundary tri groups: {len(dups)}</p>")

    open(args.out_html, "w").write("\n".join(html))
    print("report ->", args.out_html)


if __name__ == "__main__":
    main()
