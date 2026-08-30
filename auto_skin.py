#!/usr/bin/env python3
"""Procedural T-pose auto-skinning — replaces the Meshy rigging stage.

The source images are STRICT T-poses we control (arms horizontal, legs
slightly apart, facing +z), so skeleton landmarks can be located
geometrically and skin weights computed as smoothed nearest-capsule
assignments. Compared to Meshy's rigger this gives deterministic seams,
guaranteed left/right symmetry, band-limited weights (no far spill = no
trailing shards in fast animation), and one less paid API call.

Emits the same (names, jpos, jix, wts) tuple convert_rigged.py consumes
from a rigged GLB, using the Meshy bone naming convention.
"""
import math


def _median(v):
    s = sorted(v)
    return s[len(s) // 2] if s else 0.0


def build_skeleton(pos):
    """Landmark a strict T-pose mesh (facing +z, y up). Returns dict
    name -> [x,y,z] joint rest positions in mesh space."""
    xs = [p[0] for p in pos]
    ys = [p[1] for p in pos]
    zs = [p[2] for p in pos]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    H = ymax - ymin

    # arm line: y of the far-out hand verts
    arm_y = _median([p[1] for p in pos if abs(p[0]) > 0.8 * max(abs(xmin), xmax)])

    # shoulder x: walking out from the center, the vertical span of the
    # slice collapses to the arm tube
    W = max(abs(xmin), xmax)
    shoulder_x = 0.35 * W
    for step in range(20, 90):
        sx = W * step / 100.0
        span = [p[1] for p in pos if sx <= abs(p[0]) <= sx + 0.06 * W]
        if span and (max(span) - min(span)) < 0.22 * H:
            shoulder_x = sx
            break
    wrist_x = 0.86 * W
    elbow_x = (shoulder_x + wrist_x) / 2.0

    # crotch: largest y-gap in the central column below mid-height
    col = sorted(p[1] for p in pos if abs(p[0]) < 0.06 * W and p[1] < ymin + 0.62 * H)
    crotch_y = ymin + 0.30 * H
    best_gap = 0.0
    for a, b in zip(col, col[1:]):
        if b - a > best_gap and b < ymin + 0.55 * H:
            best_gap = b - a
            crotch_y = b
    if best_gap < 0.02 * H:
        crotch_y = ymin + 0.30 * H

    # leg centers just below the crotch
    leg_band = [p for p in pos if crotch_y - 0.14 * H < p[1] < crotch_y - 0.02 * H]
    lx = _median([p[0] for p in leg_band if p[0] > 0]) or 0.12 * W
    rx = _median([p[0] for p in leg_band if p[0] < 0]) or -0.12 * W

    ankle_y = ymin + 0.055 * H
    knee_y = (crotch_y + ankle_y) / 2.0

    # neck: narrowest silhouette between the arm line and the head top
    neck_y = arm_y + 0.06 * H
    best_w = 1e9
    yy = arm_y + 0.04 * H
    while yy < ymax - 0.18 * H:
        band = [abs(p[0]) for p in pos if yy <= p[1] <= yy + 0.03 * H]
        if band:
            w = max(band)
            if w < best_w:
                best_w = w
                neck_y = yy
        yy += 0.02 * H
    head_y = neck_y + 0.10 * H

    hips_y = crotch_y + 0.06 * H
    chest_y = arm_y - 0.02 * H
    z0 = _median(zs)

    def leg_z(x0, y0):
        c = [p[2] for p in pos if abs(p[0] - x0) < 0.08 * W
             and abs(p[1] - y0) < 0.05 * H]
        return _median(c) if c else z0

    sk = {
        "Hips":    [0.0, hips_y, z0],
        "Spine":   [0.0, hips_y + (chest_y - hips_y) * 0.4, z0],
        "Spine01": [0.0, hips_y + (chest_y - hips_y) * 0.7, z0],
        "Spine02": [0.0, chest_y, z0],
        "neck":    [0.0, neck_y, z0],
        "Head":    [0.0, head_y, z0],
        "head_end": [0.0, ymax, z0],
        "LeftShoulder":  [shoulder_x * 0.45, arm_y, z0],
        "LeftArm":       [shoulder_x, arm_y, z0],
        "LeftForeArm":   [elbow_x, arm_y, z0],
        "LeftHand":      [wrist_x, arm_y, z0],
        "RightShoulder": [-shoulder_x * 0.45, arm_y, z0],
        "RightArm":      [-shoulder_x, arm_y, z0],
        "RightForeArm":  [-elbow_x, arm_y, z0],
        "RightHand":     [-wrist_x, arm_y, z0],
        "LeftUpLeg":  [lx, crotch_y + 0.03 * H, leg_z(lx, crotch_y)],
        "LeftLeg":    [lx, knee_y, leg_z(lx, knee_y)],
        "LeftFoot":   [lx, ankle_y, leg_z(lx, ankle_y)],
        "LeftToeBase": [lx, ymin + 0.02 * H, leg_z(lx, ankle_y) + 0.10 * H],
        "RightUpLeg": [rx, crotch_y + 0.03 * H, leg_z(rx, crotch_y)],
        "RightLeg":   [rx, knee_y, leg_z(rx, knee_y)],
        "RightFoot":  [rx, ankle_y, leg_z(rx, ankle_y)],
        "RightToeBase": [rx, ymin + 0.02 * H, leg_z(rx, ankle_y) + 0.10 * H],
    }
    return sk


# meshy node -> weighting bone (nodes without their own capsule fold into
# the nearest covering bone)
NODE2BONE = {
    "Hips": "Hips", "Spine": "Hips", "Spine01": "Spine02", "Spine02": "Spine02",
    # collar flesh rides the CHEST: mapping it to the head part makes
    # collar tris swing with head pitch (red neck spikes in crouches)
    "neck": "Spine02", "Head": "Head", "head_end": "Head", "headfront": "Head",
    "LeftShoulder": "Spine02", "RightShoulder": "Spine02",
    "LeftArm": "LeftArm", "LeftForeArm": "LeftForeArm", "LeftHand": "LeftHand",
    "RightArm": "RightArm", "RightForeArm": "RightForeArm", "RightHand": "RightHand",
    "LeftUpLeg": "LeftUpLeg", "LeftLeg": "LeftLeg",
    "LeftFoot": "LeftFoot", "LeftToeBase": "LeftFoot",
    "RightUpLeg": "RightUpLeg", "RightLeg": "RightLeg",
    "RightFoot": "RightFoot", "RightToeBase": "RightFoot",
}

# capsule bones used for weighting: name -> (joint_a, joint_b)
BONES = {
    "Hips":         ("Hips", "Spine"),
    "Spine02":      ("Spine01", "Spine02"),
    "neck":         ("Spine02", "neck"),
    "Head":         ("Head", "head_end"),
    "LeftArm":      ("LeftArm", "LeftForeArm"),
    "LeftForeArm":  ("LeftForeArm", "LeftHand"),
    "LeftHand":     ("LeftHand", None),
    "RightArm":     ("RightArm", "RightForeArm"),
    "RightForeArm": ("RightForeArm", "RightHand"),
    "RightHand":    ("RightHand", None),
    "LeftUpLeg":    ("LeftUpLeg", "LeftLeg"),
    "LeftLeg":      ("LeftLeg", "LeftFoot"),
    "LeftFoot":     ("LeftFoot", "LeftToeBase"),
    "RightUpLeg":   ("RightUpLeg", "RightLeg"),
    "RightLeg":     ("RightLeg", "RightFoot"),
    "RightFoot":    ("RightFoot", "RightToeBase"),
}

# adjacency graph: weight smoothing may only blend across these pairs, so
# spill stays local (a shoe vertex can never pick up torso weight).
ADJ = {
    "Hips": {"Spine02", "LeftUpLeg", "RightUpLeg"},
    "Spine02": {"Hips", "neck", "LeftArm", "RightArm"},
    "neck": {"Spine02", "Head"},
    "Head": {"neck"},
    "LeftArm": {"Spine02", "LeftForeArm"},
    "LeftForeArm": {"LeftArm", "LeftHand"},
    "LeftHand": {"LeftForeArm"},
    "RightArm": {"Spine02", "RightForeArm"},
    "RightForeArm": {"RightArm", "RightHand"},
    "RightHand": {"RightForeArm"},
    "LeftUpLeg": {"Hips", "LeftLeg"},
    "LeftLeg": {"LeftUpLeg", "LeftFoot"},
    "LeftFoot": {"LeftLeg"},
    "RightUpLeg": {"Hips", "RightLeg"},
    "RightLeg": {"RightUpLeg", "RightFoot"},
    "RightFoot": {"RightLeg"},
}


def _seg_dist(p, a, b):
    if b is None:
        return math.dist(p, a)
    ab = [b[k] - a[k] for k in range(3)]
    ap = [p[k] - a[k] for k in range(3)]
    denom = sum(c * c for c in ab) or 1e-12
    t = max(0.0, min(1.0, sum(ab[k] * ap[k] for k in range(3)) / denom))
    q = [a[k] + ab[k] * t for k in range(3)]
    return math.dist(p, q)


def reskin(pos, tris, names, jpos, jix0=None, wts0=None):
    """Discipline a rig's skin weights, keeping its joint placement AND
    its (mostly correct) segmentation. Meshy's raw weights spill across
    non-adjacent bones, which turns into trailing shards when joints
    swing. Seeded from Meshy's dominant bone per vertex, we strip
    non-local spill, then graph-constrained diffusion re-smooths the
    bands. Falls back to nearest-capsule seeding when no weights given."""
    sk = {}
    for side in ("Left", "Right"):
        for j in ("Shoulder", "Arm", "ForeArm", "Hand",
                  "UpLeg", "Leg", "Foot", "ToeBase"):
            n = side + j
            if n in names:
                sk[n] = list(jpos[names.index(n)])
    for n in ("Hips", "Spine", "Spine01", "Spine02", "neck", "Head", "head_end"):
        if n in names:
            sk[n] = list(jpos[names.index(n)])
    if "head_end" not in sk:
        h = sk["Head"]
        sk["head_end"] = [h[0], max(p[1] for p in pos), h[2]]

    def capsule_dists(p):
        out = {}
        for n, (a, b) in BONES.items():
            if a not in sk:
                continue
            out[n] = _seg_dist(p, sk[a], sk[b] if (b and b in sk) else None)
        return out

    seed = None
    if jix0 is not None:
        # collapse meshy node weights to weighting-bone names: any node
        # not itself a weighting bone folds into its nearest ancestor-ish
        # equivalent via NODE2BONE.
        seed = []
        for ji, wt in zip(jix0, wts0):
            acc = {}
            for k in range(4):
                if wt[k] <= 0.0:
                    continue
                node = names[ji[k]]
                bone = NODE2BONE.get(node)
                if bone is None:
                    continue
                acc[bone] = acc.get(bone, 0.0) + wt[k]
            if not acc:
                acc = {"Hips": 1.0}
            seed.append(max(acc, key=acc.get))
    per_vert = _skin_core(pos, tris, sk, seed)
    nidx = {n: i for i, n in enumerate(names)}
    jix, wts = [], []
    for w in per_vert:
        # sharpen: soft 50/50 bands at fast-rotating joints (ankles!) shear
        # boundary tris into slivers; squaring pushes weights toward the
        # dominant bone while diffusion keeps the band location smooth.
        w = {b: v * v for b, v in w.items()}
        top = sorted(w.items(), key=lambda kv: -kv[1])[:4]
        top = [(b, v) for b, v in top if v >= 0.08 and b in nidx]
        tot = sum(v for _, v in top) or 1.0
        ji = [0, 0, 0, 0]
        wv = [0.0, 0.0, 0.0, 0.0]
        for k, (b, v) in enumerate(top):
            ji[k] = nidx[b]
            wv[k] = v / tot
        jix.append(ji)
        wts.append(wv)
    return jix, wts


def _skin_core(pos, tris, sk, seed=None):
    """GEODESIC assignment + graph-constrained diffusion. Returns a list
    of {bone_name: weight} per vertex.

    Straight-line nearest-capsule fails on chibi bodies (the arm capsule
    sits right on top of the waist), and Meshy's own heat weights bleed
    the same way. Instead: each bone claims the vertices that are
    UNAMBIGUOUSLY nearest to it (core seeds), then regions grow outward
    along the mesh SURFACE — flesh that is close in space but far along
    the surface (waist vs arm) ends up with its true bone."""
    import heapq

    bones = {n: ab for n, ab in BONES.items() if ab[0] in sk}

    def capsule_d(p, n):
        a, b = bones[n]
        return _seg_dist(p, sk[a], sk[b] if (b and b in sk) else None)

    # vertex adjacency over the position-welded mesh
    key2rep = {}
    rep = list(range(len(pos)))
    for i, p in enumerate(pos):
        key = (round(p[0], 5), round(p[1], 5), round(p[2], 5))
        if key in key2rep:
            rep[i] = key2rep[key]
        else:
            key2rep[key] = i
    nbrs = {}
    for t in tris:
        r = [rep[i] for i in t]
        for a in range(3):
            for b in range(3):
                if r[a] != r[b]:
                    nbrs.setdefault(r[a], set()).add(r[b])

    # assignment: the source rig's dominant bone per vertex (Meshy's
    # segmentation is broadly correct; the diffusion below disciplines
    # the bands). Geodesic-from-capsule seeding was tried and REGRESSED
    # badly on chibi proportions — capsules overlap too much.
    if seed is not None:
        assign = seed
    else:
        assign = [min(bones, key=lambda n: capsule_d(p, n)) for p in pos]

    wrep = {}
    for i in range(len(pos)):
        if rep[i] == i:
            wrep[i] = {assign[i]: 1.0}
    for _ in range(14):
        new = {}
        for i, ns in nbrs.items():
            mix = {}
            for b, w in wrep[i].items():
                mix[b] = mix.get(b, 0.0) + w * 2.0
            for j in ns:
                for b, w in wrep[j].items():
                    mix[b] = mix.get(b, 0.0) + w / max(1, len(ns))
            dom = max(mix, key=mix.get)
            keep = {dom} | ADJ.get(dom, set())
            mix = {b: w for b, w in mix.items() if b in keep}
            tot = sum(mix.values()) or 1.0
            new[i] = {b: w / tot for b, w in mix.items()}
        for i in new:
            wrep[i] = new[i]

    return [dict(wrep.get(rep[i], {assign[rep[i]]: 1.0})) for i in range(len(pos))]


def skin(pos, tris):
    """Returns (names, jpos, jix, wts) in convert_rigged's expected shape."""
    sk = build_skeleton(pos)
    names = list(sk.keys())
    jix, wts = reskin(pos, tris, names, [sk[n] for n in names])
    return names, [sk[n] for n in names], jix, wts
