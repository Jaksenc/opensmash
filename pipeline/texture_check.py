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
                        [--target mario|samus|luigi|link|...]
Needs tpose.png, rigged.glb, and the target bundle in the character
dir (bundle.json for mario, bundle-<target>.json for a retarget).

Retarget caveat: every posed row is the SYNTHESIZED T-pose, which
straightens the target skeleton out of its bind pose. The further that
bind pose sits from a T (Samus's arms fold across the chest), the more
the rows exaggerate thinly-owned bones — check a tear against the
in-game clip captures before calling it a conversion defect.
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

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.dirname(PIPELINE_DIR)

# camera angles: front / rear / top-down (yaw, pitch)
VIEWS = [("front", -90, 0), ("rear", 90, 0), ("top", -90, 90)]


def target_paths(chardir, slug, target):
    """(bundle, osb, fkind) for a retarget. Mario is the default staging
    (bundle.json / <slug>.osb); every other skeleton is staged beside it
    as bundle-<target>.json / <slug>-<target>.osb."""
    if target == "mario":
        return (os.path.join(chardir, "bundle.json"),
                os.path.join(HERE, "play", f"{slug}.osb"), 0)
    prof = os.path.join(HERE, "skels", f"{target}.profile.json")
    if not os.path.exists(prof):
        sys.exit(f"unknown target {target!r}: no {prof}")
    return (os.path.join(chardir, f"bundle-{target}.json"),
            os.path.join(HERE, "play", f"{slug}-{target}.osb"),
            int(json.load(open(prof))["fkind"]))


def vanilla_ghost(yaw, pitch, size, target="mario"):
    """Proportions ghost of the vanilla conform TARGET in the same
    synthesized T-pose. The vanilla part dump is too sparse to mesh
    directly (hulls read as disconnected blobs), so each part renders as
    a smooth ellipsoid: axis along the bone, radius measured from the
    dump. Flat colors so the row reads at a glance; it is a proportions
    reference, not a faithful vanilla render."""
    import numpy as np
    try:
        from .preview_bundle import load_skeleton
    except ImportError:
        from preview_bundle import load_skeleton

    # the canonical part dumps are keyed in Mario's joint numbering, so
    # the blob layout below is target-independent; only the origins move
    # (pulled from the target skeleton through the profile's joint map).
    if target == "mario":
        parts_path = os.path.join(HERE, "skels", "parts", "vanilla-mario-parts.json")
        skel_path = os.path.join(HERE, "skels", "reference", "mario.skel")
        jmap = None
    else:
        parts_path = os.path.join(HERE, "skels", "parts", f"vanilla-{target}-parts.canonical.json")
        skel_path = os.path.join(HERE, "skels", f"{target}.skel")
        jmap = {int(k): int(v) for k, v in json.load(open(os.path.join(
            HERE, "skels", f"{target}.profile.json")))["map"].items()}
    parts = {int(k): np.array(v, float) for k, v in
             json.load(open(parts_path)).items()}
    skel = load_skeleton(skel_path)
    O = {j: np.array(o, float) for j, (o, _) in skel.items()}
    if jmap:
        O = {cj: np.array(skel[tj][0], float)
             for cj, tj in jmap.items() if tj in skel}

    def frame_from_x(t, up_hint):
        # orthonormal row basis (row-vector convention) with local +x -> t
        t = np.array(t, float); t /= np.linalg.norm(t)
        u = np.array(up_hint, float)
        u = u - (u @ t) * t
        u /= np.linalg.norm(u)
        return np.stack([t, u, np.cross(t, u)])

    def part_radius(j):
        # median perpendicular distance from the part's local bone axis (+x)
        v = parts.get(j)
        if v is None or not len(v):
            return 20.0
        return float(np.median(np.hypot(v[:, 1], v[:, 2])))

    def part_halfext(j):
        v = parts.get(j)
        if v is None or not len(v):
            return np.array([25.0, 25.0, 25.0])
        return (v.max(0) - v.min(0)) / 2.0

    o6 = O[6]
    fwd = np.array([1.0, 0.0, 0.0])
    up_w = np.array([0.0, 1.0, 0.0])

    SKIN = (247, 202, 160)
    RED = (214, 60, 48)
    BLUE = (60, 92, 200)
    WHITE = (245, 245, 245)
    BROWN = (120, 68, 40)
    if target != "mario":
        # proportions only — neutral tones so nobody reads the ghost as a
        # color reference for a fighter that isn't Mario
        RED, BLUE = (152, 152, 160), (108, 108, 120)
        WHITE, BROWN = (216, 216, 222), (88, 88, 96)

    # (center, row-frame, semi-axes xyz in that frame, color)
    blobs = []
    he6 = part_halfext(6)
    blobs.append((o6 + np.array([0.0, he6[1] * 0.1, 0.0]),
                  frame_from_x(fwd, up_w), he6[[0, 1, 2]], BLUE))
    he12 = part_halfext(12)
    hc = o6 + np.array([0.0, np.linalg.norm(O[12] - o6) + he12[1] * 0.55, 0.0])
    blobs.append((hc, frame_from_x(fwd, up_w),
                  np.array([he12[0], he12[1] * 0.75, he12[2] * 0.8]), RED))

    for chain, side in (((8, 9, 10), -1.0), ((14, 15, 16), 1.0),
                        ((19, 20, 22), -1.0), ((24, 25, 27), 1.0)):
        j0, j1, j2 = chain
        arm = j0 in (8, 14)
        t = np.array((0.0, 0.0, side) if arm else (0.0, -1.0, 0.15 * side))
        t /= np.linalg.norm(t)
        R = frame_from_x(t, up_w if arm else fwd)
        off = O[j0] - o6
        o0 = o6 + np.array([0.0, off[1], side * math.hypot(off[0], off[2])])
        L1 = np.linalg.norm(O[j1] - O[j0])
        L2 = np.linalg.norm(O[j2] - O[j1])
        o1 = o0 + L1 * t
        o2 = o1 + L2 * t
        r0, r1 = part_radius(j0), part_radius(j1)
        limb_col = RED if arm else BLUE
        # one capsule-ish ellipsoid per bone segment, spanning joint to joint
        blobs.append(((o0 + o1) / 2, R,
                      np.array([L1/2 + r0*0.3, r0, r0]), limb_col))
        blobs.append(((o1 + o2) / 2, R,
                      np.array([L2/2 + r1*0.3, r1, r1]), limb_col))
        # extremity: gloves are spheres, boots stretch forward
        hex_ = part_halfext(j2)
        if arm:
            r2 = float(hex_.mean()) * 0.9
            blobs.append((o2 + t * r2 * 0.4, frame_from_x(t, up_w),
                          np.array([r2, r2, r2]), WHITE))
        else:
            blobs.append((o2 + fwd * hex_[0] * 0.35, frame_from_x(fwd, up_w),
                          np.array([hex_[0], hex_[1] * 0.8, hex_[2]]), BROWN))

    # unit sphere mesh shared by every ellipsoid
    NLAT, NLON = 10, 14
    sv, st = [], []
    for i in range(NLAT + 1):
        th = math.pi * i / NLAT
        for k in range(NLON):
            ph = 2 * math.pi * k / NLON
            sv.append((math.sin(th) * math.cos(ph),
                       math.cos(th),
                       math.sin(th) * math.sin(ph)))
    for i in range(NLAT):
        for k in range(NLON):
            a = i * NLON + k
            b = i * NLON + (k + 1) % NLON
            c = (i + 1) * NLON + k
            d = (i + 1) * NLON + (k + 1) % NLON
            st.append((a, b, c))
            st.append((b, d, c))
    sv = np.array(sv)

    world, tris, cols = [], [], []
    for center, R, ax, col in blobs:
        base = len(world)
        world.extend((sv * ax) @ R + center)
        tris.extend((base + a, base + b, base + c) for a, b, c in st)
        cols.extend([col] * len(st))

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
    img = Image.new("RGB", (size, size), (255, 255, 255))
    dr = ImageDraw.Draw(img)
    order = []
    for ti, t3 in enumerate(tris):
        s = [(size/2 + (rpos[i][0]-xc)*sc, size/2 - (rpos[i][1]-yc)*sc,
              rpos[i][2]) for i in t3]
        order.append((sum(p[2] for p in s)/3, ti, s))
    order.sort(key=lambda x: x[0])
    for _, ti, s in order:
        a, b, c = (rpos[i] for i in tris[ti])
        n = np.cross(b-a, c-a)
        nl = np.linalg.norm(n) or 1e-9
        sh = 0.55 + 0.45 * abs(float(n @ L)) / nl
        col = tuple(min(255, int(cc * sh)) for cc in cols[ti])
        dr.polygon([(p[0], p[1]) for p in s], fill=col)
    return img


def crop_fighter(im, pad=30):
    """Tight crop to the fighter against a uniform capture background."""
    import numpy as np
    a = np.asarray(im.convert("RGB")).astype(int)
    mask = np.abs(a - a[8, 8]).sum(axis=2) > 40
    mask[:8, :] = mask[-8:, :] = False     # frame border isn't the fighter
    mask[:, :8] = mask[:, -8:] = False
    ys, xs = np.where(mask)
    if not len(xs):
        return im
    return im.crop((max(xs.min()-pad, 0), max(ys.min()-pad, 0),
                    min(xs.max()+pad, im.width), min(ys.max()+pad, im.height)))


def vanilla_idle_capture(fkind=0):
    """Newest cached vanilla pose-capture idle frame for this fighter
    kind, cropped."""
    cells = sorted(glob.glob(os.path.join(
        HERE, f"eval/cells/pose-vanilla-fk{fkind}-*/frame_800.png")),
                   key=os.path.getmtime)
    if not cells:
        return None
    return crop_fighter(Image.open(cells[-1]).convert("RGB"))


def engine_tpose(bundle_json, osb, tmp, fkind=0, target="mario"):
    """True in-engine renders of the converted character frozen in the
    SAME synthesized T-pose (SSB64_POSE_OVERRIDE hook): real engine
    lighting, RGBA16 quantization, filtering. The camera is pinned on the
    character's axis per view (SSB64_CAM_PLAN), so front/rear are square
    and the top view is a genuine overhead. Returns {view: cropped Image}
    or {} if the capture fails."""
    out = {}
    # ONE boot for all views: the override file carries one pose section
    # per view (POSEAT frame=N) and the camera plan repositions the pinned
    # camera in step. No joint=0 line -> poses render at absolute dump
    # coordinates, immune to the animation.
    CX, CZ = -1755.0, 0.0        # stage center of the eval boot
    bf = json.load(open(bundle_json))["skinned"]["bind_frames"]
    cy = float(bf["6"]["o"][1])   # chest height ~ character center
    D = 900.0
    # the engine's camera breaks down past ~50 degrees of downward tilt,
    # so the true top-down splits the angle: camera 45 down + pose leaned
    # 45 back = looking straight along the character's up axis
    T = D / math.sqrt(2.0)
    views = (
        ("front", 90, 0, 320, (CX, cy, D), (CX, cy, CZ)),
        ("rear", -90, 0, 360, (CX, cy, D), (CX, cy, CZ)),
        ("top", 90, 45, 400, (CX, cy + 30 + T, T), (CX, cy + 30, CZ)),
    )
    combined = os.path.join(tmp, "tpose-views.skel")
    try:
        plan = []
        with open(combined, "w") as fc:
            for view, spin, tip, frame, eye, at in views:
                skel = os.path.join(tmp, f"tpose-{view}.skel")
                subprocess.run([sys.executable,
                                os.path.join(PIPELINE_DIR, "preview_bundle.py"),
                                bundle_json, os.path.join(tmp, "_pose_scratch.png"),
                                "--tpose", "--unlit", "--size", "120",
                                "--dump-frames", skel, "--dump-yaw", str(spin),
                                "--dump-pitch", str(tip),
                                "--dump-at", f"{CX},{CZ}",
                                "--target", target],
                               check=True, cwd=HERE, capture_output=True)
                fc.write(f"POSEAT frame={frame - 20}\n")
                fc.write(open(skel).read())
                plan.append(f"{frame - 20}:{eye[0]},{eye[1]},{eye[2]}"
                            f":{at[0]},{at[1]},{at[2]}")
        shots = os.path.join(tmp, "engine-views")
        env = dict(os.environ)
        env["SSB64_POSE_OVERRIDE"] = combined
        env["SSB64_CAM_PLAN"] = ";".join(plan)
        cmd = [sys.executable, os.path.join(PIPELINE_DIR, "run_eval.py"),
               shots, "--bundle", osb, "--fkind", str(fkind),
               "--frames-list", ",".join(str(v[3]) for v in views),
               "--pose", "--width", "1280"]
        # fighter kinds are baked into the replay (capture_clip.py
        # convention) — a mario tour on another fkind never boots
        rpl = os.path.join(HERE, "eval", "fixtures", "replays", f"eval-tour-fk{fkind}.rpl")
        if fkind and os.path.exists(rpl):
            cmd += ["--replay", rpl]
        subprocess.run(cmd,
                       check=True, cwd=HERE, env=env, capture_output=True)
        for view, _, _, frame, _, _ in views:
            out[view] = crop_fighter(
                Image.open(os.path.join(shots, f"frame_{frame}.png")))
    except Exception as e:
        print(f"engine t-pose capture failed: {e}")
    return out


def run(script, src, out, yaw, pitch, unlit, extra=()):
    cmd = [sys.executable, os.path.join(PIPELINE_DIR, script), src, out,
           "--yaw", str(yaw), "--pitch", str(pitch), *extra]
    if unlit:
        cmd.append("--unlit")
    subprocess.run(cmd, check=True, cwd=HERE, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chardir", help="character dir (play/ui/<slug>)")
    ap.add_argument("out", nargs="?", default=None)
    ap.add_argument("--size", type=int, default=700, help="panel height px")
    ap.add_argument("--target", default="mario",
                    help="conform target skeleton to check "
                         "(mario/samus/luigi/link/... — any skels/*.profile.json)")
    ap.add_argument("--no-engine", action="store_true",
                    help="skip the true in-engine same-pose renders "
                         "(they boot the game twice, ~1 min)")
    args = ap.parse_args()

    d = args.chardir.rstrip("/")
    slug = os.path.basename(d)
    target = args.target
    suffix = "" if target == "mario" else f"-{target}"
    out_path = args.out or os.path.join(d, f"texture_check{suffix}.png")
    tpose = os.path.join(d, "tpose.png")
    glb = os.path.join(d, "rigged.glb")
    bundle, osb, fkind = target_paths(d, slug, target)
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
            extra=("--tpose", "--target", target))
        cells[("game", name)] = p
        p = os.path.join(tmp, f"heat-{name}.png")
        run("preview_bundle.py", bundle, p, yaw, pitch, unlit=False,
            extra=("--tpose", "--target", target, "--heat"))
        cells[("heat", name)] = p
    shaded = os.path.join(tmp, "glb-shaded.png")
    run("render_textured.py", glb, shaded, -90, 0, unlit=False)

    H = args.size
    def fit(path):
        im = Image.open(path).convert("RGB")
        return im.resize((int(im.width * H / im.height), H), Image.LANCZOS)

    # ownership-hardness heat at the true bind pose (reference column):
    # what the engine binds against, no synthesized-pose exaggeration
    heat_bind = os.path.join(tmp, "heat-bind.png")
    skel = os.path.join(HERE, "skels", "reference", "mario.skel") if target == "mario" else \
        os.path.join(HERE, "skels", f"{target}.skel")
    subprocess.run([sys.executable, os.path.join(PIPELINE_DIR, "preview_bundle.py"),
                    bundle, skel, heat_bind, "--heat", "--yaw", "-90"],
                   check=True, cwd=HERE, capture_output=True)

    grid = [
        [(fit(tpose), "source image (gpt-image-2)")]
        + [(fit(cells[("glb", n)]), f"meshified GLB, unlit - {n}")
           for n, _, _ in VIEWS],
        [(fit(shaded), "meshified GLB, flat-shaded")]
        + [(fit(cells[("game", n)]), f"in-game texture (OSB5), unlit - {n}")
           for n, _, _ in VIEWS],
        [(fit(heat_bind), "ownership heat @ bind (blue=solid, red=50/50)")]
        + [(fit(cells[("heat", n)]), f"ownership heat, T-pose - {n}")
           for n, _, _ in VIEWS],
    ]
    def fit_im(im):
        return im.resize((int(im.width * H / im.height), H), Image.LANCZOS)

    # row 3: the ENGINE drawing the shipped .osb frozen in the same pose —
    # closes the presentation gap (real lighting, RGBA16, filtering)
    if not args.no_engine and os.path.exists(osb):
        eng = engine_tpose(bundle, osb, tmp, fkind, target)
        if eng:
            blank = Image.new("RGB", (H // 2, H), (255, 255, 255))
            row = [(blank, "")]
            for view in ("front", "rear", "top"):
                if view in eng:
                    row.append((fit_im(eng[view]),
                                f"ENGINE render, same pose - {view}"))
            while len(row) < 4:
                row.append((blank, ""))
            grid.append(row)
    elif not args.no_engine:
        print(f"no {osb} — skipping engine renders")

    # vanilla row — the conform target's true proportions
    idle = vanilla_idle_capture(fkind)
    ref = (fit_im(idle), f"vanilla {target}, in-engine idle") if idle else \
          (Image.new("RGB", (H, H), (255, 255, 255)),
           f"no vanilla fk{fkind} capture cached")
    grid.append([ref] + [(fit_im(vanilla_ghost(yaw, pitch, 900, target)),
                          f"vanilla {target} proportions - {n}")
                         for n, yaw, pitch in VIEWS])

    PAD, LBL = 30, 42
    rows = len(grid)
    col_w = [max(grid[r][c][0].width for r in range(rows)) for c in range(4)]
    W = sum(col_w) + PAD * 5 + PAD          # extra PAD around the rule
    row_h = LBL + H
    out = Image.new("RGB", (W, PAD + rows * (row_h + PAD)), (255, 255, 255))
    dr = ImageDraw.Draw(out)
    for r, row in enumerate(grid):
        y = PAD + r * (row_h + PAD)
        x = PAD
        for c, (im, label) in enumerate(row):
            cx = x + (col_w[c] - im.width) // 2
            dr.text((x, y + 8), label, fill=(20, 20, 20))
            out.paste(im, (cx, y + LBL))
            x += col_w[c] + PAD
            if c == 0:
                x += PAD           # room for the separator rule
    rx = PAD + col_w[0] + PAD
    dr.line([(rx + PAD // 2, PAD), (rx + PAD // 2, out.height - PAD)],
            fill=(70, 70, 85), width=3)
    dr.text((PAD, out.height - PAD + 6), f"{slug} -> {target}",
            fill=(120, 120, 130))
    out.save(out_path)
    print(f"texture check -> {out_path}")


if __name__ == "__main__":
    main()
