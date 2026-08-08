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
    nrm = (read_accessor(gltf, bin_, prim["attributes"]["NORMAL"])
           if "NORMAL" in prim["attributes"] else None)
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
    return pos, nrm, uv, tris, img, jix, wts, names, jpos


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
    pos, nrm, uv, tris, img, jix, wts, names, jpos = load_rigged(glb_path)
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

    # ---- per-part conform transforms (ANISOTROPIC):
    #   v_world = Q * (u*(u.(v-a))*s_ax + ((v-a) - u*(u.(v-a)))*s_perp) + A
    # s_ax   = mario_bone_len / mesh_bone_len  (bone endpoints land EXACTLY
    #          on mario joints -> no gaps, animation reads correctly)
    # s_perp = ONE global scale (median of s_ax over real bones) so the
    #          character keeps its own thickness/volume. Per-bone UNIFORM
    #          scale shredded chibi-proportioned characters: stubby legs
    #          needed x330 while the torso got x184, and adjacent parts
    #          disagreed by ~1.8x (the shredded-Mao root cause).
    conf = {}
    ax_scales = []
    for part, (prox, dist) in seg.items():
        if part in INHERIT or dist is None:
            continue
        a = jpos[name_idx[prox]]
        b = jpos[name_idx[dist]]
        mb = mario_bone[part]
        A, B = frames[part][0], frames[mb][0]
        mv = [b[i]-a[i] for i in range(3)]
        Mv = [B[i]-A[i] for i in range(3)]
        mlen = math.sqrt(sum(c*c for c in mv)) or 1e-9
        Mlen = math.sqrt(sum(c*c for c in Mv)) or 1e-9
        ax_scales.append(Mlen/mlen)
    ax_sorted = sorted(ax_scales)
    s_perp = ax_sorted[len(ax_sorted)//2]

    for part, (prox, dist) in seg.items():
        a = jpos[name_idx[prox]]
        if part in INHERIT:
            continue
        b = jpos[name_idx[dist]]
        mb = mario_bone[part]
        A, B = frames[part][0], frames[mb][0]
        mv = [b[i]-a[i] for i in range(3)]
        Mv = [B[i]-A[i] for i in range(3)]
        mlen = math.sqrt(sum(c*c for c in mv)) or 1e-9
        Mlen = math.sqrt(sum(c*c for c in Mv)) or 1e-9
        Q = rot_between(mv, Mv)
        u = [c/mlen for c in mv]
        conf[part] = (Q, Mlen/mlen, s_perp, u, a, A)

    # distal parts (head/hands/feet): parent's rotation, isotropic global
    # scale (no bone to span), own anchors
    for part in INHERIT:
        parent = INHERIT[part]
        Qp = conf[parent][0]
        a = jpos[name_idx[seg[part][0]]]
        A = frames[part][0]
        conf[part] = (Qp, s_perp, s_perp, [0.0, 1.0, 0.0], a, A)

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
        Q, s_ax, sp, u, a, A = conf[part]
        tgt = bone_target.get(bname)
        if tgt is not None:
            a = jpos[name_idx[bname]]
            A = tgt
        d = [v[k]-a[k] for k in range(3)]
        ax = d[0]*u[0] + d[1]*u[1] + d[2]*u[2]
        d = [u[k]*ax*s_ax + (d[k] - u[k]*ax)*sp for k in range(3)]
        d = mat_apply(Q, d)
        return [d[k] + A[k] for k in range(3)]

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
    OVERLAP_W = 0.2
    parts = {}       # dominant-assignment tris (island-filtered below)
    overlap = {}     # overlap-band copies (NEVER island-filtered: they are
                     # coincident with real geometry, and thin bands get
                     # wrongly deleted as "specks" leaving holes at seams)
    for t in tris:
        owners = {vpart[i] for i in t}
        for j in owners:
            parts.setdefault(j, []).append(t)
        # overlap copies only where EVERY vertex holds real weight in the
        # part — one-vertex copies turn into trailing slivers when the
        # neighboring joint swings away.
        cand = set(vweights[t[0]].keys())
        for i in t[1:]:
            cand &= set(vweights[i].keys())
        for part in cand:
            if all(vweights[i].get(part, 0.0) >= OVERLAP_W for i in t):
                overlap.setdefault(part, []).append(t)

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
    for j, rt in overlap.items():
        have = set(map(tuple, parts.get(j, [])))
        parts.setdefault(j, []).extend(t for t in rt if tuple(t) not in have)

    # ---- baked diffuse: per-vertex shade from the GLB normal rotated by
    # the dominant part's conform rotation, lit by a fixed key light. The
    # OSB3 path multiplies texture * shade (G_CC_MODULATEIA); vanilla N64
    # fighters are lit, so unlit texture reads as a flat cutout.
    LIGHT = normalize([0.35, 0.75, 0.55])

    def vshade(i):
        if nrm is None:
            return 1.0
        Q = conf[vpart[i]][0]
        n = mat_apply(Q, list(nrm[i]))
        ln = math.sqrt(sum(c*c for c in n)) or 1e-9
        d = sum(n[k]*LIGHT[k] for k in range(3)) / ln
        return min(1.0, 0.55 + 0.45*max(0.0, d))

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
            sh = vshade(gi)
            r, g, b = (int(c*sh) for c in vcolor(gi)[:3])
            u, vv = uv[gi]
            overts.append([round(d[0], 2), round(d[1], 2), round(d[2], 2),
                           r, g, b,
                           round(min(1.0, max(0.0, u)), 4),
                           round(min(1.0, max(0.0, vv)), 4),
                           int(sh*255)])
        out_parts.append({
            "joint": joint, "region": str(joint), "verts": overts,
            "tris": [[remap[a], remap[b], remap[c]] for a, b, c in rtris],
        })

    # ---- atlas: dilate UV-island colors into the unused gutters BEFORE
    # downscaling, else the downscale (and in-game bilinear sampling)
    # averages across island borders — black hair texels bleed into the
    # face and suit as dark flecks. Coverage = rasterized UV triangles.
    atlas_path = out_path.rsplit(".", 1)[0] + "-atlas.png"
    if img is not None:
        import numpy as np
        from PIL import ImageDraw
        AW = 1024
        base = img.resize((AW, AW), Image.LANCZOS)
        cov = Image.new("L", (AW, AW), 0)
        cd = ImageDraw.Draw(cov)
        for t in tris:
            cd.polygon([(min(AW-1, max(0, uv[i][0]*AW)),
                         min(AW-1, max(0, uv[i][1]*AW))) for i in t], fill=255)
        arr = np.asarray(base, dtype=np.float32)
        known = np.asarray(cov, dtype=np.float32) / 255.0
        for _ in range(14):
            ksum = (np.roll(known, 1, 0) + np.roll(known, -1, 0)
                    + np.roll(known, 1, 1) + np.roll(known, -1, 1))
            csum = (np.roll(arr*known[..., None], 1, 0) + np.roll(arr*known[..., None], -1, 0)
                    + np.roll(arr*known[..., None], 1, 1) + np.roll(arr*known[..., None], -1, 1))
            fill = ksum > 0
            grow = fill & (known < 0.5)
            arr[grow] = (csum[grow] / ksum[grow, None])
            known[fill] = 1.0
        Image.fromarray(arr.astype(np.uint8)).resize(
            (512, 512), Image.LANCZOS).save(atlas_path)

    json.dump({"parts": out_parts, "atlas": atlas_path.rsplit("/", 1)[-1]},
              open(out_path, "w"))
    nv = sum(len(p["verts"]) for p in out_parts)
    nt = sum(len(p["tris"]) for p in out_parts)
    print(f"bundle v9 (rigged retarget): {len(out_parts)} parts, "
          f"{nv} verts, {nt} tris -> {out_path}")
    for p in out_parts:
        print(f"  joint {p['joint']:>2}: {len(p['verts']):5d} v {len(p['tris']):5d} t")


def write_binary3(bundle_json_path, out_path):
    """OSB3: textured bundle.

    Layout (all little-endian):
      'OSB3', u32 nparts, u32 texW, u32 texH,
      texW*texH u16 RGBA16 texels stored BIG-endian byte pairs (N64 order),
      per part: u32 joint, u32 nbatches,
        per batch: u32 nverts, u32 ntris,
          verts: s16 x,y,z,s,t (s/t in s10.5 texel units) + u8 shade + u8 pad,
          tris:  u8 a,b,c,pad.
    Triangles pre-batched to <=30 unique verts per gSPVertex window.
    """
    d = json.load(open(bundle_json_path))
    base = bundle_json_path.rsplit("/", 1)[0]
    atlas = Image.open((base + "/" if base != bundle_json_path else "")
                       + d["atlas"]).convert("RGBA")
    TW, TH = atlas.size
    px = atlas.load()

    with open(out_path, "wb") as f:
        f.write(b"OSB3")
        f.write(struct.pack("<III", len(d["parts"]), TW, TH))
        for y in range(TH):
            row = bytearray()
            for x in range(TW):
                r, g, b, a = px[x, y]
                p16 = ((r >> 3) << 11) | ((g >> 3) << 6) | ((b >> 3) << 1) | (1 if a >= 128 else 0)
                row.append(p16 >> 8)
                row.append(p16 & 0xFF)
            f.write(row)

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
            f.write(struct.pack("<II", p["joint"], len(batches)))
            for bverts, btris in batches:
                f.write(struct.pack("<II", len(bverts), len(btris)))
                for v in bverts:
                    x, y, z = (int(round(v[k])) for k in range(3))
                    u, vv, shade = v[6], v[7], v[8]
                    s = max(0, min(TW*32 - 1, int(round(u * TW * 32))))
                    t = max(0, min(TH*32 - 1, int(round(vv * TH * 32))))
                    f.write(struct.pack("<hhhhhBB", x, y, z, s, t, shade, 0))
                for t3 in btris:
                    f.write(struct.pack("<BBBB", t3[0], t3[1], t3[2], 0))
        print(f"batches: {total_b}, atlas {TW}x{TH}")
    print("binary3:", out_path)


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--binary":
        write_binary(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 4 and sys.argv[1] == "--binary3":
        write_binary3(sys.argv[2], sys.argv[3])
    else:
        main()
