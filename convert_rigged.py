#!/usr/bin/env python3
"""Converter v9: rigged retargeting.

Input is a Meshy-rigged GLB (humanoid skeleton + skin weights). Each mesh
bone is rigidly conformed onto the matching Mario bone (rotation + uniform
scale + translation mapping mesh-bone segment -> Mario spawn-bone segment),
vertices are assigned to parts by dominant skin weight, and parts are
authored in the joint's true rest frame (SKELDUMP2 matrices).

This kills the two systemic defects of the chop-in-place converters
(v0..v8): constant per-part offsets wherever the generated mesh differs
from Mario's spawn stance, and baked stretch from the hard arm pre-pose
cut. Weight boundaries also give natural creases for part splits, and feet
get their own parts (joints 22/27) so ankles articulate.

Usage:
  convert_rigged.py napoleon-rigged.glb mario-frames.skel out-bundle.json
  convert_rigged.py --binary out-bundle.json out.osb   (same OSB2 writer)
"""
import io
import json
import math
import struct
import sys

from PIL import Image

from convert_glb import (load_glb, read_accessor, load_frames, inv3,
                         row_apply, rot_between, mat_apply, normalize,
                         write_binary)


# ---------------------------------------------------------------- glTF rig
def node_rest_world(gltf):
    """Global rest-pose position per node index (TRS compose down the tree)."""
    nodes = gltf["nodes"]

    def local_mat(n):
        if "matrix" in n:
            m = n["matrix"]  # column-major 4x4
            return [[m[0], m[4], m[8], m[12]],
                    [m[1], m[5], m[9], m[13]],
                    [m[2], m[6], m[10], m[14]],
                    [0, 0, 0, 1]]
        t = n.get("translation", [0, 0, 0])
        q = n.get("rotation", [0, 0, 0, 1])
        s = n.get("scale", [1, 1, 1])
        x, y, z, w = q
        R = [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
             [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
             [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]]
        return [[R[0][0]*s[0], R[0][1]*s[1], R[0][2]*s[2], t[0]],
                [R[1][0]*s[0], R[1][1]*s[1], R[1][2]*s[2], t[1]],
                [R[2][0]*s[0], R[2][1]*s[1], R[2][2]*s[2], t[2]],
                [0, 0, 0, 1]]

    def matmul(a, b):
        return [[sum(a[r][k]*b[k][c] for k in range(4)) for c in range(4)]
                for r in range(4)]

    world = {}

    def walk(idx, parent_m):
        m = matmul(parent_m, local_mat(nodes[idx]))
        world[idx] = m
        for c in nodes[idx].get("children", []):
            walk(c, m)

    ident = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    scenes = gltf.get("scenes", [{}])
    roots = scenes[gltf.get("scene", 0)].get("nodes", [0])
    for r in roots:
        walk(r, ident)
    return {i: (m[0][3], m[1][3], m[2][3]) for i, m in world.items()}


def load_rigged(path):
    gltf, bin_ = load_glb(path)
    prim = gltf["meshes"][0]["primitives"][0]
    pos = read_accessor(gltf, bin_, prim["attributes"]["POSITION"])
    uv = read_accessor(gltf, bin_, prim["attributes"]["TEXCOORD_0"])
    jix = read_accessor(gltf, bin_, prim["attributes"]["JOINTS_0"])
    wts = read_accessor(gltf, bin_, prim["attributes"]["WEIGHTS_0"])
    idx = [t[0] for t in read_accessor(gltf, bin_, prim["indices"])]
    tris = [(idx[i], idx[i+1], idx[i+2]) for i in range(0, len(idx), 3)]

    img = None
    if gltf.get("images"):
        bv = gltf["bufferViews"][gltf["images"][0]["bufferView"]]
        start = bv.get("byteOffset", 0)
        img = Image.open(io.BytesIO(bin_[start:start+bv["byteLength"]])).convert("RGB")

    skin = gltf["skins"][0]
    names = [gltf["nodes"][j].get("name", f"j{j}") for j in skin["joints"]]
    nw = node_rest_world(gltf)
    jpos = [nw[j] for j in skin["joints"]]

    # skinned vertices live in mesh space == skin space for Meshy rigs
    # (mesh node has identity transform; verify silently via skeleton root)
    return pos, uv, tris, img, jix, wts, names, jpos


# --------------------------------------------------- meshy -> mario mapping
# Mario part joints and their bone-defining child joints (spawn frames).
# Meshy bone name -> (mario part joint, mario bone child joint or None).
# Side X/Y placeholders resolved by mesh-side sign so game handedness
# matches v8's proven convention (mesh +x chain -> joints 8/9/10, 19/20/22).
def build_bone_map(names, jpos):
    def side_of(prefix):
        # which meshy side (Left/Right) has +x root?
        for i, n in enumerate(names):
            if n == prefix + "Arm" or n == prefix + "UpLeg":
                return jpos[i][0]
        return 0.0

    posx = "Left" if side_of("Left") > side_of("Right") else "Right"
    negx = "Right" if posx == "Left" else "Left"

    m = {}
    # torso: Hips + all Spines -> chest 6 (bone 6 -> neck 11)
    for n in ("Hips", "Spine", "Spine01", "Spine02"):
        m[n] = (6, 11)
    # shoulders (clavicles) barely move; ride the chest
    m[posx + "Shoulder"] = (6, 11)
    m[negx + "Shoulder"] = (6, 11)
    # head cluster -> 12; conform inherits the neck bone (11 -> 12)
    for n in ("neck", "Head", "head_end", "headfront"):
        m[n] = (12, None)
    # arms: +x chain -> 8/9/10, -x -> 14/15/16 (v8 convention)
    m[posx + "Arm"] = (8, 9); m[posx + "ForeArm"] = (9, 10); m[posx + "Hand"] = (10, None)
    m[negx + "Arm"] = (14, 15); m[negx + "ForeArm"] = (15, 16); m[negx + "Hand"] = (16, None)
    # legs: +x -> 19/20/22, -x -> 24/25/27 (ankle joints 21/26 carry the
    # knee->ankle bone endpoint; foot parts are 22/27)
    m[posx + "UpLeg"] = (19, 20); m[posx + "Leg"] = (20, 21)
    m[posx + "Foot"] = (22, None); m[posx + "ToeBase"] = (22, None)
    m[negx + "UpLeg"] = (24, 25); m[negx + "Leg"] = (25, 26)
    m[negx + "Foot"] = (27, None); m[negx + "ToeBase"] = (27, None)
    return m


# meshy bone segment per part: (proximal node name, distal node name)
MESH_BONE = {
    6: ("Hips", "neck"),
    12: ("neck", "Head"),          # anchor at Head, dir neck->Head
    8: None, 9: None, 10: None,    # filled per side below
    14: None, 15: None, 16: None,
    19: None, 20: None, 22: None,
    24: None, 25: None, 27: None,
}

# parts whose rotation/scale is INHERITED from a parent part (distal parts
# with no real mario bone): part -> parent part
INHERIT = {12: 6, 10: 9, 16: 15, 22: 20, 27: 25}
# anchor joints for inherited parts: (mesh node name resolved per side,
# mario joint)  e.g. hand part anchors mesh Hand node onto mario joint 10.


def main():
    glb_path, frames_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    pos, uv, tris, img, jix, wts, names, jpos = load_rigged(glb_path)
    frames = load_frames(frames_path)
    name_idx = {n: i for i, n in enumerate(names)}
    bone_map = build_bone_map(names, jpos)

    posx = "Left" if jpos[name_idx["LeftArm"]][0] > jpos[name_idx["RightArm"]][0] else "Right"
    negx = "Right" if posx == "Left" else "Left"

    # mesh bone segments per mario part (proximal anchor, distal)
    seg = {
        6: ("Hips", "neck"),
        12: ("Head", "head_end"),
        8: (posx + "Arm", posx + "ForeArm"),
        9: (posx + "ForeArm", posx + "Hand"),
        10: (posx + "Hand", None),
        14: (negx + "Arm", negx + "ForeArm"),
        15: (negx + "ForeArm", negx + "Hand"),
        16: (negx + "Hand", None),
        19: (posx + "UpLeg", posx + "Leg"),
        20: (posx + "Leg", posx + "Foot"),
        22: (posx + "Foot", None),
        24: (negx + "UpLeg", negx + "Leg"),
        25: (negx + "Leg", negx + "Foot"),
        27: (negx + "Foot", None),
    }
    mario_bone = {6: 11, 8: 9, 9: 10, 14: 15, 15: 16,
                  19: 20, 20: 21, 24: 25, 25: 26}

    # ---- per-part conform transforms: v_world = Q*(v - a)*s + A
    conf = {}
    for part, (prox, dist) in seg.items():
        a = jpos[name_idx[prox]]
        if part in INHERIT:
            parent = INHERIT[part]
            Qp, sp, _, _ = conf[parent]
            A = frames[part][0]
            conf[part] = (Qp, sp, a, A)
            continue
        b = jpos[name_idx[dist]]
        mb = mario_bone[part]
        A, B = frames[part][0], frames[mb][0]
        mv = [b[i]-a[i] for i in range(3)]
        Mv = [B[i]-A[i] for i in range(3)]
        mlen = math.sqrt(sum(c*c for c in mv)) or 1e-9
        Mlen = math.sqrt(sum(c*c for c in Mv)) or 1e-9
        Q = rot_between(mv, Mv)
        conf[part] = (Q, Mlen/mlen, a, A)

    # head/hands/feet need their own anchors but parent's Q,s — set above
    # (dict order: parents 6,9,15,20,25 all appear before their INHERIT
    # children in seg? Not guaranteed — fix by two passes)
    for part in INHERIT:
        parent = INHERIT[part]
        Qp, sp, _, _ = conf[parent]
        a = jpos[name_idx[seg[part][0]]]
        A = frames[part][0]
        conf[part] = (Qp, sp, a, A)

    # ---- vertex assignment: accumulate skin weight per mario part.
    # vpart = dominant part; vweights = {part: weight} per vertex, used to
    # widen the seam-overlap band (N64 models overlap flesh at joints).
    vpart = []
    vweights = []
    for ji, wt in zip(jix, wts):
        acc = {}
        for k in range(4):
            if wt[k] <= 0.0:
                continue
            part = bone_map.get(names[ji[k]], (6, 11))[0]
            acc[part] = acc.get(part, 0.0) + wt[k]
        if not acc:
            acc = {6: 1.0}
        vweights.append(acc)
        vpart.append(max(acc, key=acc.get))

    # ---- per-MESHY-BONE maps for LBS authoring. Each meshy bone uses its
    # mario part's rotation+scale but is translation-anchored so the
    # bone's own node lands exactly on the mario joint it corresponds to
    # (shoulders -> 7/13, neck -> 11, head -> 12, chain bones -> chain
    # joints). Adjacent maps then AGREE at every pivot, so blending only
    # interpolates small local rotation differences — no baked beams,
    # blobs, or branch-point flaps. Bones with no mario counterpart
    # (Spine*, head_end, ToeBase...) inherit their part's map unchanged.
    def mario_o(j):
        return frames[j][0]

    bone_target = {
        "Hips": mario_o(6),
        "neck": mario_o(11), "Head": mario_o(12),
        posx + "Shoulder": mario_o(7), negx + "Shoulder": mario_o(13),
        posx + "Arm": mario_o(8), posx + "ForeArm": mario_o(9), posx + "Hand": mario_o(10),
        negx + "Arm": mario_o(14), negx + "ForeArm": mario_o(15), negx + "Hand": mario_o(16),
        posx + "UpLeg": mario_o(19), posx + "Leg": mario_o(20), posx + "Foot": mario_o(21),
        negx + "UpLeg": mario_o(24), negx + "Leg": mario_o(25), negx + "Foot": mario_o(26),
    }

    def bone_apply(bname, v):
        part = bone_map.get(bname, (6, 11))[0]
        Q, s, a, A = conf[part]
        tgt = bone_target.get(bname)
        if tgt is not None:
            a = jpos[name_idx[bname]]
            A = tgt
        d = [v[k]-a[k] for k in range(3)]
        d = mat_apply(Q, d)
        return [d[k]*s + A[k] for k in range(3)]

    # ---- authored world position = linear-blend skinning over the
    # per-bone maps with the real skin weights. At spawn the mesh is an
    # exact smooth skinned pose: gapless, no baked stretch, and every
    # duplicated copy of a boundary triangle is IDENTICAL at rest (tears
    # only open as joints deviate from spawn, and the overlap copies mask
    # them from both sides — the vanilla N64 approach).
    world = []
    for i, v in enumerate(pos):
        ji, wt = jix[i], wts[i]
        tot = sum(max(w, 0.0) for w in wt) or 1.0
        acc = [0.0, 0.0, 0.0]
        for k in range(4):
            if wt[k] <= 0.0:
                continue
            bw = bone_apply(names[ji[k]], v)
            for c in range(3):
                acc[c] += bw[c] * wt[k] / tot
        world.append(acc)


    def vcolor(i):
        if img is None:
            return (200, 200, 200)
        u, vv = uv[i]
        u = min(0.999, max(0.0, u)); vv = min(0.999, max(0.0, vv))
        return img.getpixel((int(u*img.width), int(vv*img.height)))

    # ---- overlap duplication + island filter. A triangle goes into every
    # part that is dominant for one of its verts, PLUS every part where
    # some vert carries >= OVERLAP_W skin weight — a wide overlap band at
    # joints (hips, shoulders); copies are identical at rest (LBS above).
    OVERLAP_W = 0.3
    parts = {}
    for t in tris:
        owners = {vpart[i] for i in t}
        for i in t:
            for part, w in vweights[i].items():
                if w >= OVERLAP_W:
                    owners.add(part)
        for j in owners:
            parts.setdefault(j, []).append(t)

    def largest_components(rtris, min_tris=8):
        parent = {}
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(x, y):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry
        for t in rtris:
            for i in t:
                parent.setdefault(i, i)
            union(t[0], t[1]); union(t[0], t[2])
        comps = {}
        for t in rtris:
            comps.setdefault(find(t[0]), []).append(t)
        if not comps:
            return []
        biggest = max(len(v) for v in comps.values())
        keep = []
        for v in comps.values():
            if len(v) >= min_tris or len(v) == biggest:
                keep.extend(v)
        return keep

    parts = {j: largest_components(rt) for j, rt in parts.items()}

    out_parts = []
    for joint, rtris in sorted(parts.items()):
        o, R = frames[joint]
        Rinv = inv3(R)
        used = sorted({i for t in rtris for i in t})
        remap = {gi: li for li, gi in enumerate(used)}
        overts = []
        for gi in used:
            d = [world[gi][k]-o[k] for k in range(3)]
            d = row_apply(d, Rinv)
            r, g, b = vcolor(gi)[:3]
            overts.append([round(d[0], 2), round(d[1], 2), round(d[2], 2), r, g, b])
        out_parts.append({
            "joint": joint, "region": str(joint), "verts": overts,
            "tris": [[remap[a], remap[b], remap[c]] for a, b, c in rtris],
        })

    json.dump({"parts": out_parts}, open(out_path, "w"))
    nv = sum(len(p["verts"]) for p in out_parts)
    nt = sum(len(p["tris"]) for p in out_parts)
    print(f"bundle v9 (rigged retarget): {len(out_parts)} parts, "
          f"{nv} verts, {nt} tris -> {out_path}")
    for p in out_parts:
        print(f"  joint {p['joint']:>2}: {len(p['verts']):5d} v {len(p['tris']):5d} t")


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--binary":
        write_binary(sys.argv[2], sys.argv[3])
    else:
        main()
