#!/usr/bin/env python3
"""OpenSmash converter: T-pose character GLB -> per-joint rigid part bundle.

Chops a generated T-pose humanoid mesh into the 16 DL-bearing joints of a
Smash 64 fighter skeleton (Mario layout) and emits each part's triangles in
its joint's local frame, scaled to the game bone lengths from a SKELDUMP.

v0b scope: vertex colors sampled from the GLB's basecolor texture (no
texture mapping in-game — Gouraud parts, authentic N64 look).

Usage:
  convert_glb.py model.glb skeldump.txt out_bundle.json

Bundle format (JSON): { parts: [ { joint: int, verts: [[x,y,z,r,g,b], ...],
tris: [[a,b,c], ...] } ] }  — coordinates are floats in joint-local space
(game units); the port loader quantizes to Vtx.
"""
import json
import math
import struct
import sys
import io
import re

from PIL import Image


# ---------------------------------------------------------------- GLB parse
def load_glb(path):
    data = open(path, "rb").read()
    magic, _ver, _total = struct.unpack("<III", data[:12])
    assert magic == 0x46546C67, "not a GLB"
    off = 12
    gltf = None
    binchunk = None
    while off < len(data):
        clen, ctype = struct.unpack("<II", data[off:off + 8])
        chunk = data[off + 8:off + 8 + clen]
        if ctype == 0x4E4F534A:
            gltf = json.loads(chunk)
        elif ctype == 0x004E4942:
            binchunk = chunk
        off += 8 + clen
    return gltf, binchunk


def read_accessor(gltf, binchunk, idx):
    acc = gltf["accessors"][idx]
    bv = gltf["bufferViews"][acc["bufferView"]]
    start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    comp = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}[acc["componentType"]]
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[acc["type"]]
    n = acc["count"]
    fmt = "<" + comp * ncomp * n
    vals = struct.unpack_from(fmt, binchunk, start)
    return [vals[i * ncomp:(i + 1) * ncomp] for i in range(n)]


def load_mesh(path):
    gltf, binchunk = load_glb(path)
    prim = gltf["meshes"][0]["primitives"][0]
    pos = read_accessor(gltf, binchunk, prim["attributes"]["POSITION"])
    uv = read_accessor(gltf, binchunk, prim["attributes"]["TEXCOORD_0"])
    idx = [t[0] for t in read_accessor(gltf, binchunk, prim["indices"])]
    tris = [(idx[i], idx[i + 1], idx[i + 2]) for i in range(0, len(idx), 3)]
    # basecolor image
    img = None
    if gltf.get("images"):
        bv = gltf["bufferViews"][gltf["images"][0]["bufferView"]]
        start = bv.get("byteOffset", 0)
        raw = binchunk[start:start + bv["byteLength"]]
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    return pos, uv, tris, img


# ------------------------------------------------------------ skeleton parse
def load_skeleton(path):
    joints = {}
    pat = re.compile(
        r"SKELDUMP: joint=(\d+) parent=(-?\d+) world=\(([^)]+)\) local=\(([^)]+)\) dl=(\S+)")
    for line in open(path):
        m = pat.search(line)
        if m:
            ji = int(m.group(1))
            joints[ji] = {
                "parent": int(m.group(2)),
                "world": [float(x) for x in m.group(3).split(",")],
                "local": [float(x) for x in m.group(4).split(",")],
                "dl": m.group(5) != "0x0",
            }
    return joints




def load_frames(path):
    """SKELDUMP2 lines -> {joint: (o, R)} with R rows = world basis vectors
    (row-vector convention: world = local . R + o)."""
    frames = {}
    pat = re.compile(r"SKELDUMP2: joint=(\d+) o=\(([^)]+)\) x=\(([^)]+)\) y=\(([^)]+)\) z=\(([^)]+)\)")
    for line in open(path):
        m = pat.search(line)
        if m:
            j = int(m.group(1))
            o = [float(v) for v in m.group(2).split(",")]
            R = [[float(v) for v in m.group(k).split(",")] for k in (3, 4, 5)]
            frames[j] = (o, R)
    return frames


def inv3(m):
    a, b, c = m[0]; d, e, f = m[1]; g, h, i = m[2]
    A = e*i - f*h; B = -(d*i - f*g); C = d*h - e*g
    det = a*A + b*B + c*C
    if abs(det) < 1e-12:
        det = 1e-12
    return [[A/det, -(b*i - c*h)/det, (b*f - c*e)/det],
            [B/det, (a*i - c*g)/det, -(a*f - c*d)/det],
            [C/det, -(a*h - b*g)/det, (a*e - b*d)/det]]


def row_apply(v, m):
    """Row-vector times matrix: v . m"""
    return [v[0]*m[0][i] + v[1]*m[1][i] + v[2]*m[2][i] for i in range(3)]


# --------------------------------------------------- semantic chop (T-pose)
# Region predicates in normalized mesh space: x right+, y up+, z forward+,
# height normalized to [0,1] (feet=0, head top=1), width to arm span.
# Part -> (joint, predicate). Predicates are evaluated per-vertex; each
# vertex belongs to the first matching region (order matters).
def classify(v, bb):
    x, y, z = v
    h = (y - bb["ymin"]) / (bb["ymax"] - bb["ymin"])       # 0..1 height
    xr = x / bb["xmax"] if bb["xmax"] else 0                # -1..1 span
    SH = 0.78    # shoulder height    (T-pose humanoid heuristics)
    HIP = 0.52   # hip height
    KNEE = 0.28  # knee height
    NECK = 0.84
    ARM_X = 0.18     # torso half-width; beyond = arm
    ELBOW_X = 0.55   # fraction of arm span
    HAND_X = 0.80

    if abs(xr) > ARM_X and h > SH - 0.12:
        side = "r" if xr > 0 else "l"
        a = abs(xr)
        if a > HAND_X:
            return side + "hand"
        if a > ELBOW_X:
            return side + "forearm"
        return side + "upperarm"
    if h > NECK:
        return "head"
    if h > SH - 0.02:
        return "neck"
    if h > HIP:
        return "chest"
    if h > KNEE + 0.08:
        return side_of(x) + "thigh"
    return side_of(x) + "shin"


def side_of(x):
    return "r" if x > 0 else "l"


# Mario-layout joint assignment for the 16 DL joints (from SKELDUMP hierarchy):
#   6 chest | 8 r-shoulder(upperarm) 9 r-forearm 10 r-hand | 12 head
#   14 l-upperarm 15 l-forearm 16 l-hand | 19 r-thigh 20 r-shin 22 r-foot
#   24 l-thigh 25 l-shin 27 l-foot
# neck folds into head; feet fold into shins (v0b simplification).
REGION_TO_JOINT = {
    "chest": 6, "neck": 12, "head": 12,
    "rupperarm": 8, "rforearm": 9, "rhand": 10,
    "lupperarm": 14, "lforearm": 15, "lhand": 16,
    "rthigh": 19, "rshin": 20,
    "lthigh": 24, "lshin": 25,
}

# Bone axis per region in MESH space (T-pose): direction from proximal
# joint towards distal end. Arms point +-x, everything else -y (down)
# except head (+y).
REGION_AXIS = {
    "chest": (0, 1, 0), "neck": (0, 1, 0), "head": (0, 1, 0),
    "rupperarm": (1, 0, 0), "rforearm": (1, 0, 0), "rhand": (1, 0, 0),
    "lupperarm": (-1, 0, 0), "lforearm": (-1, 0, 0), "lhand": (-1, 0, 0),
    "rthigh": (0, -1, 0), "rshin": (0, -1, 0),
    "lthigh": (0, -1, 0), "lshin": (0, -1, 0),
}


def bone_vec_for_joint(joints, j):
    """Game bone vector for joint j = local translate of its first child
    with geometry (falls back to a downward stub)."""
    for cj, info in sorted(joints.items()):
        if info["parent"] == j:
            v = info["local"]
            if any(abs(c) > 1e-3 for c in v):
                return v
    return [0.0, -20.0, 0.0]


def normalize(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return [c / n for c in v]


def rot_between(a, b):
    """Rotation matrix taking unit vector a to unit vector b (Rodrigues)."""
    a, b = normalize(list(a)), normalize(list(b))
    v = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
    c = sum(x * y for x, y in zip(a, b))
    if c < -0.9999:  # opposite: rotate 180 about any perpendicular
        p = normalize([a[1], -a[0], 0] if abs(a[2]) < 0.9 else [0, -a[2], a[1]])
        x, y, z = p
        return [[2*x*x-1, 2*x*y, 2*x*z], [2*x*y, 2*y*y-1, 2*y*z], [2*x*z, 2*y*z, 2*z*z-1]]
    k = 1.0 / (1.0 + c)
    return [
        [c + v[0]*v[0]*k, v[0]*v[1]*k - v[2], v[0]*v[2]*k + v[1]],
        [v[1]*v[0]*k + v[2], c + v[1]*v[1]*k, v[1]*v[2]*k - v[0]],
        [v[2]*v[0]*k - v[1], v[2]*v[1]*k + v[0], c + v[2]*v[2]*k],
    ]


def mat_apply(m, v):
    return [sum(m[r][i] * v[i] for i in range(3)) for r in range(3)]


def main():
    glb_path, skel_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    frames_path = sys.argv[4] if len(sys.argv) > 4 else None
    pos, uv, tris, img = load_mesh(glb_path)
    joints = load_skeleton(skel_path) if not frames_path else None
    frames = load_frames(frames_path) if frames_path else None

    xs = [p[0] for p in pos]; ys = [p[1] for p in pos]
    bb = {"xmax": max(abs(min(xs)), abs(max(xs))), "ymin": min(ys), "ymax": max(ys)}
    vreg = [classify(p, bb) for p in pos]

    # world origins per joint (from frames when present)
    def jworld(j):
        return frames[j][0] if frames else joints[j]["world"]

    all_j = sorted(frames.keys() if frames else joints.keys())
    jys = [jworld(j)[1] for j in all_j]
    ground = min(jys) - 8.0
    head_y = max(jys)
    skel_height = (head_y - ground) * 1.22
    S = skel_height / (bb["ymax"] - bb["ymin"])
    root_x = jworld(0)[0] if 0 in all_j else 0.0

    def to_world(v):
        return [root_x + v[0] * S, ground + (v[1] - bb["ymin"]) * S, v[2] * S]

    posed = [list(p) for p in pos]
    for side, sh_j, hand_j, sign in (("r", 8, 10, 1), ("l", 14, 16, -1)):
        if sh_j not in all_j or hand_j not in all_j:
            continue
        sh_w, hd_w = jworld(sh_j), jworld(hand_j)
        target = normalize([hd_w[i] - sh_w[i] for i in range(3)])
        R = rot_between((sign, 0, 0), target)
        pivot = [(sh_w[0] - root_x) / S, (sh_w[1] - ground) / S + bb["ymin"], sh_w[2] / S]
        arm_regions = {side + "upperarm", side + "forearm", side + "hand"}
        for i, r in enumerate(vreg):
            if r in arm_regions:
                d = [posed[i][k] - pivot[k] for k in range(3)]
                d = mat_apply(R, d)
                posed[i] = [pivot[k] + d[k] for k in range(3)]

    def vcolor(i):
        if img is None:
            return (200, 200, 200)
        u, v = uv[i]
        u = min(0.999, max(0.0, u)); v = min(0.999, max(0.0, v))
        return img.getpixel((int(u * img.width), int(v * img.height)))

    parts = {}
    for t in tris:
        regs = [vreg[i] for i in t]
        # strict assignment: seam-crossing tris become gaps (authentic N64
        # joint separation) instead of stretching into spikes when the two
        # joint frames diverge under animation.
        if regs[0] == regs[1] == regs[2] and regs[0] in REGION_TO_JOINT:
            parts.setdefault(regs[0], []).append(t)

    out_parts = []
    for reg, rtris in sorted(parts.items()):
        joint = REGION_TO_JOINT[reg]
        o = jworld(joint)
        Rinv = inv3(frames[joint][1]) if frames else None
        used = sorted({i for t in rtris for i in t})
        remap = {gi: li for li, gi in enumerate(used)}
        overts = []
        for gi in used:
            w = to_world(posed[gi])
            d = [w[k] - o[k] for k in range(3)]
            if Rinv is not None:
                d = row_apply(d, Rinv)   # into the joint's true rest frame
            r, g, b = vcolor(gi)[:3]
            overts.append([round(d[0], 2), round(d[1], 2), round(d[2], 2), r, g, b])
        out_parts.append({
            "joint": joint, "region": reg, "verts": overts,
            "tris": [[remap[a], remap[b], remap[c]] for a, b, c in rtris],
        })

    json.dump({"parts": out_parts}, open(out_path, "w"))
    print(f"bundle v4: {len(out_parts)} parts, frames={'yes' if frames else 'NO'}, scale={S:.1f} -> {out_path}")


def write_binary(bundle_json_path, out_path):
    """Emit the .osb v2 binary. Per part, triangles are pre-batched into
    groups referencing <=30 unique vertices (the F3DEX vertex-buffer
    window), with vertices duplicated across batches as needed — the
    loader emits one gSPVertex per batch and never drops triangles.

    Layout: 'OSB2', u32 nparts; per part: u32 joint, u32 nbatches;
    per batch: u32 nverts, u32 ntris, verts (s16 x,y,z u8 r,g,b,pad),
    tris (u8 a,b,c local indices + u8 pad)."""
    import struct as _s
    d = json.load(open(bundle_json_path))
    with open(out_path, "wb") as f:
        f.write(b"OSB2")
        f.write(_s.pack("<I", len(d["parts"])))
        total_b = 0
        for p in d["parts"]:
            verts, tris = p["verts"], p["tris"]
            batches = []
            cur_map, cur_verts, cur_tris = {}, [], []
            for a, b, cc in tris:
                need = [i for i in (a, b, cc) if i not in cur_map]
                if len(cur_verts) + len(need) > 30:
                    if cur_tris:
                        batches.append((cur_verts, cur_tris))
                    cur_map, cur_verts, cur_tris = {}, [], []
                    need = [i for i in (a, b, cc) if i not in cur_map]
                for i in need:
                    cur_map[i] = len(cur_verts)
                    cur_verts.append(verts[i])
                cur_tris.append((cur_map[a], cur_map[b], cur_map[cc]))
            if cur_tris:
                batches.append((cur_verts, cur_tris))
            total_b += len(batches)
            f.write(_s.pack("<II", p["joint"], len(batches)))
            for bverts, btris in batches:
                f.write(_s.pack("<II", len(bverts), len(btris)))
                for x, y, z, r, g, b2 in bverts:
                    f.write(_s.pack("<hhhBBBB", int(round(x)), int(round(y)), int(round(z)), r, g, b2, 0))
                for t in btris:
                    f.write(_s.pack("<BBBB", t[0], t[1], t[2], 0))
        print("batches:", total_b)
    print("binary:", out_path)


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--binary":
        write_binary(sys.argv[2], sys.argv[3])
    else:
        main()
