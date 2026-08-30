#!/usr/bin/env python3
"""Faithful software render of a converted character bundle assembled on a
SKELDUMP skeleton: per-pixel affine sampling of the bundle atlas through the
verts' global atlas UVs — the same texture data the in-game OSB loader draws.
Painter's algorithm; optional flat diffuse light (default) or --unlit for
texture-only artifact hunting.

Usage: preview_bundle.py bundle.json skeldump.txt out.png
           [--yaw DEG] [--pitch DEG] [--size PX] [--unlit] [--parts 8,9,10]
"""
import argparse
import json
import math
import os
import re
import sys

from PIL import Image, ImageDraw


def load_skeleton(path):
    """Prefers SKELDUMP2 full frames; falls back to SKELDUMP positions.
    Returns {joint: (o, R|None)}."""
    joints = {}
    pat2 = re.compile(r"SKELDUMP2: joint=(\d+) o=\(([^)]+)\) x=\(([^)]+)\) y=\(([^)]+)\) z=\(([^)]+)\)")
    pat1 = re.compile(r"SKELDUMP: joint=(\d+) parent=(-?\d+) world=\(([^)]+)\)")
    for line in open(path):
        m = pat2.search(line)
        if m:
            j = int(m.group(1))
            o = [float(v) for v in m.group(2).split(",")]
            R = [[float(v) for v in m.group(k).split(",")] for k in (3, 4, 5)]
            joints[j] = (o, R)
            continue
        m = pat1.search(line)
        if m and int(m.group(1)) not in joints:
            joints[int(m.group(1))] = ([float(x) for x in m.group(3).split(",")], None)
    return joints


def tpose_frames(skinned, atlas=None, jmap=None):
    """Synthesize T-pose joint frames from the bundle's bind skeleton:
    chest/head uprighted (Procrustes to world axes, conform scale kept),
    arm chains aimed lateral, leg chains straight down, limb twist chosen
    so each frame's forward axis matches the chest facing. Offline eval
    only — nothing here touches game data.

    The chain layout below is written in Mario's joint numbering. For a
    bundle retargeted onto another skeleton, pass that profile's
    canonical->target `jmap`: frames and vertex weights are looked up
    through it and the result comes back keyed by target joint."""
    import numpy as np
    T = {int(j): (np.array(f["o"], float), np.array(f["R"], float))
         for j, f in skinned["bind_frames"].items()}
    c2t = ({int(k): int(v) for k, v in jmap.items()} if jmap
           else {j: j for j in T})
    F = {cj: T[tj] for cj, tj in c2t.items() if tj in T}
    F.update({j: f for j, f in T.items() if j not in c2t.values()})

    def aim(d, t):
        # minimal row-vector rotation Q with d@Q = t (Rodrigues)
        d = d/np.linalg.norm(d); t = np.array(t, float)
        v = np.cross(d, t); c = float(d@t); s = np.linalg.norm(v)
        if s < 1e-8:
            return np.eye(3) if c > 0 else -np.eye(3)
        v = v/s
        K = np.array([[0, v[2], -v[1]], [-v[2], 0, v[0]], [v[1], -v[0], 0]])
        return np.eye(3)*c + K*s + np.outer(v, v)*(1-c)

    def twist(R, axis, fwd):
        # extra rotation about `axis` aligning R's x-row with `fwd`
        x = R[0] - (R[0]@axis)*axis
        f = fwd - (fwd@axis)*axis
        if np.linalg.norm(x) < 1e-6 or np.linalg.norm(f) < 1e-6:
            return np.eye(3)
        x, f = x/np.linalg.norm(x), f/np.linalg.norm(f)
        c = float(x@f)
        s = float(np.cross(x, f)@axis)
        a = math.atan2(s, c)
        ca, sa = math.cos(a), math.sin(a)
        v = axis
        K = np.array([[0, v[2], -v[1]], [-v[2], 0, v[0]], [v[1], -v[0], 0]])
        return np.eye(3)*ca + K*sa + np.outer(v, v)*(1-ca)

    o6, R6 = F[6]

    def upright(R):
        # orthogonal Procrustes from the frame's normalized axis rows to
        # the identity basis: kills roll/pitch, but leaves an arbitrary
        # residual yaw (frame axes don't encode "forward")
        A = R / np.linalg.norm(R, axis=1, keepdims=True)
        U, _, Vt = np.linalg.svd(A.T)
        Q = U @ Vt
        if np.linalg.det(Q) < 0:   # keep a proper rotation
            U[:, -1] *= -1
            Q = U @ Vt
        return Q

    def mesh_forward(joint):
        # a joint's forward, estimated from its verts' bind-space normals
        tj = c2t.get(joint, joint)
        f = np.zeros(3)
        for v in skinned["verts"]:
            w = sum(wt for j, wt in v[8] if j == tj)
            if w > 0.5:
                f += w * np.array(v[5:8], float)
        f[1] = 0.0
        n = np.linalg.norm(f)
        return f/n if n > 1e-6 else None

    def vert_dir(cj):
        # direction from a joint's origin to the centroid of the verts it
        # owns (bind world space) — for a collapsed chain that spans two
        # canonical bones, this is the bone direction the joints lost
        tj = c2t.get(cj, cj)
        acc, wsum = np.zeros(3), 0.0
        for v in skinned["verts"]:
            w = sum(wt for j, wt in v[8] if j == tj)
            if w > 0.5:
                acc += w * np.array(v[0:3], float)
                wsum += w
        if wsum == 0.0:
            return None
        d = acc/wsum - F[cj][0]
        return d if np.linalg.norm(d) > 1e-6 else None

    up = np.array([0.0, 1.0, 0.0])

    def yaw_to(f, tgt):
        # rotation about world-up taking horizontal dir f to tgt
        a = math.atan2(float(np.cross(f, tgt) @ up), float(f @ tgt))
        ca, sa = math.cos(a), math.sin(a)
        K = np.array([[0, up[2], -up[1]], [-up[2], 0, up[0]], [up[1], -up[0], 0]])
        return np.eye(3)*ca + K*sa + np.outer(up, up)*(1-ca)

    def face_frame(joint, fwd):
        # upright the joint, then fix the residual yaw so the joint's
        # empirical mesh forward lands on `fwd`
        Q = upright(F[joint][1])
        f = mesh_forward(joint)
        if f is not None:
            Q = Q @ yaw_to(f @ Q, fwd)
        return Q

    # facing axis: keep the bind facing's x sign
    f6 = mesh_forward(6)
    fwd = np.array([1.0 if f6 is None or f6[0] >= 0 else -1.0, 0.0, 0.0])

    def skin_face_dir():
        # face direction from SKIN-colored head texels (the converter's
        # own facing cue): mean-normal estimates drift with hair bulk and
        # cheek asymmetry, but visible skin clusters on the front of the
        # head for any human character.
        if atlas is None:
            return None
        hsv = atlas.convert("HSV")
        TW, TH = atlas.size
        px = hsv.load()
        head = c2t.get(12, 12)
        pts, ctr, cn = [], np.zeros(3), 0
        for v in skinned["verts"]:
            w = sum(wt for j, wt in v[8] if j == head)
            if w <= 0.5:
                continue
            p = np.array(v[0:3])
            ctr += p; cn += 1
            h, s, val = px[min(TW-1, max(0, int(v[3]*TW))),
                           min(TH-1, max(0, int(v[4]*TH)))]
            if 3 <= h <= 30 and 35 <= s <= 190 and val >= 110:
                pts.append(p)
        if cn == 0 or len(pts) < 40:
            return None
        d = np.mean(pts, axis=0) - ctr/cn
        d[1] = 0.0
        n = np.linalg.norm(d)
        return d/n if n > 1e-6 else None

    # orient the chest by its own mesh forward; the head inherits the
    # chest's rotation plus only a yaw fix — the converter places head
    # geometry with the CHEST's rotation, so uprighting the head to its
    # own (unrelated) joint frame read as a crooked head, which the
    # in-game animations never show.
    Q6 = face_frame(6, fwd)
    f12 = skin_face_dir()
    if f12 is None:
        f12 = mesh_forward(12)
    Q12 = Q6 @ yaw_to((f12 if f12 is not None else fwd) @ Q6, fwd)

    def follow(p):                 # chest rotation applied about its origin
        return (p - o6) @ Q6 + o6

    out = {6: (o6, R6 @ Q6)}
    o12, R12 = F[12]
    out[12] = (follow(o12), R12 @ Q12)

    # root offsets and bone lengths, averaged across the left/right pair:
    # the crumpled bind pose is asymmetric, but the engine's mirrored anim
    # poses aren't — exactly mirrored frames also mean any left/right
    # difference in the render is baked into the verts/weights, not the pose
    def chainlens(c):
        return [np.linalg.norm(F[c[1]][0]-F[c[0]][0]),
                np.linalg.norm(F[c[2]][0]-F[c[1]][0])]
    sym = {}
    for a, b in (((8, 9, 10), (14, 15, 16)), ((19, 20, 22), (24, 25, 27))):
        offs = [F[c[0]][0] - o6 for c in (a, b)]
        dy = sum(o[1] for o in offs)/2
        dlat = sum(math.hypot(o[0], o[2]) for o in offs)/2
        # a collapsed chain contributes a zero-length segment; averaging
        # it in would halve the mirror bone on BOTH sides
        lens = [(x+y)/2 if min(x, y) > 1e-6 else max(x, y)
                for x, y in zip(chainlens(a), chainlens(b))]
        sym[a] = sym[b] = (dy, dlat, lens)

    for chain, side in (((8, 9, 10), -1.0), ((14, 15, 16), 1.0),
                        ((19, 20, 22), -1.0), ((24, 25, 27), 1.0)):
        j0, j1, j2 = chain
        arm = j0 in (8, 14)
        # T-pose target: arms lateral, legs straight down + slight splay
        t = np.array((0.0, 0.0, side) if arm else (0.0, -1.0, 0.15*side))
        t /= np.linalg.norm(t)
        dy, dlat, lens = sym[chain]
        o0 = o6 + np.array([0.0, dy, side*dlat])
        d01 = F[j1][0] - F[j0][0]
        Q0 = aim(d01, t)
        R0 = F[j0][1] @ Q0
        R0 = R0 @ twist(R0, t, fwd)
        o1 = o0 + lens[0]*t
        d12 = F[j2][0] - F[j1][0]
        if np.linalg.norm(d12) <= 1e-6:
            # collapsed chain (two canonical joints on one target joint,
            # e.g. Samus's cannon arm): no joint-to-joint direction, so
            # aim the shared joint by the geometry it actually carries
            d12 = vert_dir(j1)
            if d12 is None:
                d12 = d01
        Q1 = aim(d12, t)
        R1 = F[j1][1] @ Q1
        R1 = R1 @ twist(R1, t, fwd)
        o2 = o1 + lens[1]*t
        R2 = F[j2][1] @ Q1
        R2 = R2 @ twist(R2, t, fwd)
        out[j0], out[j1], out[j2] = (o0, R0), (o1, R1), (o2, R2)
    # back to target numbering; `out` is built proximal-first, so a
    # collapsed pair keeps the proximal frame (where its geometry starts)
    posed = {}
    for j, (o, R) in out.items():
        posed.setdefault(c2t.get(j, j), (o, R.tolist()))
    return posed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("skel", nargs="?", default=None)
    ap.add_argument("out")
    ap.add_argument("--yaw", type=float, default=0.0)
    ap.add_argument("--pitch", type=float, default=0.0)
    ap.add_argument("--size", type=int, default=900)
    ap.add_argument("--unlit", action="store_true")
    ap.add_argument("--parts", default=None,
                    help="comma-separated joint ids to render (default all)")
    ap.add_argument("--skinned", action="store_true",
                    help="render the OSB5 skinned mesh (what the engine "
                         "draws) instead of the rigid per-part assembly")
    ap.add_argument("--heat", action="store_true",
                    help="ownership-hardness heatmap instead of texture "
                         "(implies --skinned): blue = vert solidly owned "
                         "by one joint, yellow -> red = 50/50 blend that "
                         "will smear when the two joints move apart")
    ap.add_argument("--target", default=None, metavar="NAME",
                    help="skeleton this bundle was retargeted onto "
                         "(skels/NAME.profile.json) — needed by --tpose "
                         "for anything but mario")
    ap.add_argument("--tpose", action="store_true",
                    help="synthesize T-pose frames from the bundle's bind "
                         "skeleton instead of reading a skeldump (implies "
                         "--skinned; the skel argument may be omitted)")
    ap.add_argument("--dump-frames", default=None, metavar="OUT.skel",
                    help="also write the pose frames as SKELDUMP2 lines "
                         "(plus a joint=0 root at the pose's feet) for the "
                         "engine's SSB64_POSE_OVERRIDE eval hook")
    ap.add_argument("--dump-yaw", type=float, default=0.0,
                    help="spin the dumped pose about world-up (degrees) — "
                         "the in-game camera is fixed, so turn the pose "
                         "instead (180 = face the camera)")
    ap.add_argument("--dump-pitch", type=float, default=0.0,
                    help="tip the dumped pose about the world x axis "
                         "(after --dump-yaw); 90 lays it back so the "
                         "fixed camera sees it top-down")
    ap.add_argument("--dump-at", default=None, metavar="X,Z",
                    help="translate the dumped pose so the chest stands "
                         "over this world X,Z — center it on the game "
                         "camera's axis to avoid oblique perspective")
    args = ap.parse_args()
    if args.heat:
        args.skinned = True
    if args.tpose:
        args.skinned = True
    elif args.skel is None:
        ap.error("skel is required unless --tpose is given")

    bundle = json.load(open(args.bundle))
    tex = Image.open(os.path.join(os.path.dirname(args.bundle) or ".",
                                  bundle["atlas"])).convert("RGB")
    if args.tpose:
        jmap = None
        if args.target and args.target != "mario":
            prof = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "skels", f"{args.target}.profile.json")
            if not os.path.exists(prof):
                sys.exit(f"unknown target {args.target!r}: no {prof}")
            jmap = json.load(open(prof))["map"]
        joints = tpose_frames(bundle["skinned"], atlas=tex, jmap=jmap)
    else:
        joints = load_skeleton(args.skel)
    TW, TH = tex.size
    only = set(int(x) for x in args.parts.split(",")) if args.parts else None

    # world-space verts: (xyz, uv) per triangle
    world, tuv, tris, heat = [], [], [], []
    if args.skinned:
        import numpy as np
        s = bundle["skinned"]
        # per-joint skinning matrix: frame(skel) x inverse(bind)
        # (local->world here is row-vector convention: w = v @ R + o)
        mats = {}
        for j, bf in s["bind_frames"].items():
            j = int(j)
            fr = joints.get(j)
            if fr is None:
                continue
            fo, fR = fr
            if fR is None:
                fR = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
            Binv = np.linalg.inv(np.array(bf["R"]))
            M = Binv @ np.array(fR)
            mats[j] = (np.array(bf["o"]), M, np.array(fo))
        for v in s["verts"]:
            p = np.array(v[0:3])
            acc = np.zeros(3)
            tot = 0.0
            for j, w in v[8]:
                bo, M, fo = mats[j]
                acc += w * ((p - bo) @ M + fo)
                tot += w
            world.append(tuple(acc / (tot or 1.0)))
            tuv.append((v[3]*TW, v[4]*TH))
            heat.append(max(w for _, w in v[8]) / (tot or 1.0) if v[8] else 1.0)
        tris = [tuple(t) for t in s["tris"]]
        if args.dump_frames:
            o6 = np.array(joints[6][0])
            ya = math.radians(args.dump_yaw)
            cy, sy = math.cos(ya), math.sin(ya)
            Y = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]])
            pa = math.radians(args.dump_pitch)
            cp2, sp2 = math.cos(pa), math.sin(pa)
            P = np.array([[1.0, 0.0, 0.0], [0.0, cp2, sp2], [0.0, -sp2, cp2]])
            M = Y @ P
            cmid = np.array([o6[0], (min(p[1] for p in world) +
                                     max(p[1] for p in world)) / 2, o6[2]])
            shift = np.zeros(3)
            if args.dump_at:
                tx, tz = (float(x) for x in args.dump_at.split(","))
                shift = np.array([tx - o6[0], 0.0, tz - o6[2]])
            # NO joint=0 line: leaving the root un-overridden makes the
            # engine's local/draw transforms cancel, so the pose renders
            # at these absolute coordinates in exactly this orientation —
            # immune to the live animation's root lean/facing.
            with open(args.dump_frames, "w") as fdf:
                for j, (o, R) in sorted(joints.items()):
                    ov = (np.array(o) - cmid) @ M + cmid + shift
                    Rv = np.array(R) @ M
                    fdf.write("SKELDUMP2: joint=%d o=(%.4f,%.4f,%.4f) "
                              "x=(%.4f,%.4f,%.4f) y=(%.4f,%.4f,%.4f) "
                              "z=(%.4f,%.4f,%.4f)\n"
                              % (j, *ov, *Rv[0], *Rv[1], *Rv[2]))
            print(f"pose frames -> {args.dump_frames} "
                  f"(yaw {args.dump_yaw:g}, pitch {args.dump_pitch:g})")
    else:
        for part in bundle["parts"]:
            if only is not None and part["joint"] not in only:
                continue
            fr = joints.get(part["joint"])
            if fr is None:
                continue
            jw, R = fr
            base = len(world)
            for v in part["verts"]:
                if R is None:
                    p = (v[0] + jw[0], v[1] + jw[1], v[2] + jw[2])
                else:
                    p = (v[0]*R[0][0] + v[1]*R[1][0] + v[2]*R[2][0] + jw[0],
                         v[0]*R[0][1] + v[1]*R[1][1] + v[2]*R[2][1] + jw[1],
                         v[0]*R[0][2] + v[1]*R[1][2] + v[2]*R[2][2] + jw[2])
                world.append(p)
                tuv.append((v[6]*TW, v[7]*TH))
            for a, b, c in part["tris"]:
                tris.append((base + a, base + b, base + c))

    W = H = args.size
    yaw, pit = math.radians(args.yaw), math.radians(args.pitch)
    cs, sn = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pit), math.sin(pit)

    def rot(v):
        x = v[0]*cs + v[2]*sn
        z = -v[0]*sn + v[2]*cs
        y = v[1]*cp - z*sp
        z = v[1]*sp + z*cp
        return (x, y, z)

    rpos = [rot(v) for v in world]
    xs = [v[0] for v in rpos]
    ys = [v[1] for v in rpos]
    xc, yc = (min(xs)+max(xs))/2, (min(ys)+max(ys))/2
    ext = max(max(xs)-min(xs), max(ys)-min(ys)) or 1e-9
    sc = (H-80)/ext

    def proj(v):
        return (W/2 + (v[0]-xc)*sc, H/2 - (v[1]-yc)*sc, v[2])

    L = (-0.35, 0.5, 0.79)
    order = []
    for t in tris:
        s = [proj(rpos[i]) for i in t]
        order.append((sum(p[2] for p in s)/3, t, s))
    order.sort(key=lambda x: x[0])

    img = Image.new("RGB", (W, H), (255, 255, 255))
    for _, t, s in order:
        a, b, c = (rpos[t[0]], rpos[t[1]], rpos[t[2]])
        u = [b[k]-a[k] for k in range(3)]
        w = [c[k]-a[k] for k in range(3)]
        n = [u[1]*w[2]-u[2]*w[1], u[2]*w[0]-u[0]*w[2], u[0]*w[1]-u[1]*w[0]]
        nlen = math.sqrt(n[0]*n[0]+n[1]*n[1]+n[2]*n[2]) or 1e-9
        shade = 1.0 if args.unlit else min(1.0, 0.45 + 0.55*max(
            0.0, (n[0]*L[0]+n[1]*L[1]+n[2]*L[2])/nlen))

        x0, y0 = s[0][0], s[0][1]
        x1, y1 = s[1][0], s[1][1]
        x2, y2 = s[2][0], s[2][1]
        if args.heat:
            h = sum(heat[i] for i in t) / 3.0
            # 1.0 solid -> blue; 0.75 -> yellow; <=0.5 -> red
            f = max(0.0, min(1.0, (1.0 - h) * 2.0))
            if f < 0.5:
                g = f / 0.5
                col = (int(70 + g*(235-70)), int(110 + g*(200-110)),
                       int(220 - g*(220-60)))
            else:
                g = (f - 0.5) / 0.5
                col = (int(235 + g*(210-235)), int(200 - g*(200-45)),
                       int(60 - g*(60-40)))
            col = tuple(int(c * shade) for c in col)
            ImageDraw.Draw(img).polygon(
                [(x0, y0), (x1, y1), (x2, y2)], fill=col)
            continue
        u0, v0 = tuv[t[0]]
        u1, v1 = tuv[t[1]]
        u2, v2 = tuv[t[2]]
        det = (x1-x0)*(y2-y0)-(x2-x0)*(y1-y0)
        if abs(det) < 1e-3:
            continue
        A = ((u1-u0)*(y2-y0)-(u2-u0)*(y1-y0))/det
        B = ((u2-u0)*(x1-x0)-(u1-u0)*(x2-x0))/det
        C = u0 - A*x0 - B*y0
        D = ((v1-v0)*(y2-y0)-(v2-v0)*(y1-y0))/det
        E = ((v2-v0)*(x1-x0)-(v1-v0)*(x2-x0))/det
        F = v0 - D*x0 - E*y0

        xs2 = [x0, x1, x2]; ys2 = [y0, y1, y2]
        bx0, bx1 = max(0, int(min(xs2))), min(W-1, int(max(xs2))+1)
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
        ImageDraw.Draw(mask).polygon(
            [(x0-bx0, y0-by0), (x1-bx0, y1-by0), (x2-bx0, y2-by0)], fill=255)
        img.paste(patch, (bx0, by0), mask)

    img.save(args.out)
    print(f"textured bundle render {len(tris)} tris -> {args.out}")


if __name__ == "__main__":
    main()
