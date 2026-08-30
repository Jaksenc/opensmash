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
import os
import math
import struct
import re
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
        # resolve the BASE COLOR image through the material — multi-texture
        # exports (Tripo: NormalGL + Color + ORM) put the normal map first
        img_idx = 0
        mats = gltf.get("materials") or []
        if mats:
            bct = (mats[0].get("pbrMetallicRoughness") or {}).get("baseColorTexture")
            if bct is not None:
                img_idx = gltf["textures"][bct["index"]].get("source", 0)
        bv = gltf["bufferViews"][gltf["images"][img_idx]["bufferView"]]
        start = bv.get("byteOffset", 0)
        img = Image.open(io.BytesIO(bin_[start:start+bv["byteLength"]])).convert("RGB")

    skin = gltf["skins"][0]
    names = [gltf["nodes"][j].get("name", f"j{j}") for j in skin["joints"]]
    nw = node_rest_world(gltf)
    jpos = [nw[j] for j in skin["joints"]]

    # Recompute smooth per-vertex normals over the POSITION-WELDED mesh.
    # The GLB duplicates vertices along every UV seam, each copy carrying
    # its own normal — under real N64 Gouraud lighting the seams shade
    # discontinuously and the dense mesh reads blocky/crinkly next to the
    # vanilla fighters' broad hand-smoothed gradients. Area-weighted facet
    # accumulation shared across all co-located copies gives the clean
    # "Phong-ish" look of the originals.
    key2group = {}
    for i, p in enumerate(pos):
        key = (round(p[0], 5), round(p[1], 5), round(p[2], 5))
        key2group.setdefault(key, []).append(i)
    acc = [[0.0, 0.0, 0.0] for _ in pos]
    for a, b, c in tris:
        pa, pb, pc = pos[a], pos[b], pos[c]
        u = [pb[k]-pa[k] for k in range(3)]
        w = [pc[k]-pa[k] for k in range(3)]
        fn = [u[1]*w[2]-u[2]*w[1], u[2]*w[0]-u[0]*w[2], u[0]*w[1]-u[1]*w[0]]
        for i in (a, b, c):
            for k in range(3):
                acc[i][k] += fn[k]     # facet normal length == 2*area weight
    nrm_s = [None] * len(pos)
    for group in key2group.values():
        s = [0.0, 0.0, 0.0]
        for i in group:
            for k in range(3):
                s[k] += acc[i][k]
        ln = math.sqrt(sum(c*c for c in s)) or 1e-9
        sn = [c/ln for c in s]
        for i in group:
            nrm_s[i] = sn
    nrm = nrm_s

    # Tripo rigs use their own naming + twist bones; fold to the Meshy
    # convention so the whole retarget pipeline works unchanged.
    if "L_Thigh" in names:
        names, jpos, jix, wts = tripo_to_meshy(pos, names, jpos, jix, wts)

    # skinned vertices live in mesh space == skin space for Meshy rigs
    # (mesh node has identity transform; verify silently via skeleton root)
    pos, nrm, uv, tris, jix, wts = decimate_if_dense(pos, nrm, uv, tris, jix, wts)
    return pos, nrm, uv, tris, img, jix, wts, names, jpos


def decimate_if_dense(pos, nrm, uv, tris, jix, wts, max_verts=9000, target_tris=4200):
    """General: providers don't reliably honor face limits (a Tripo rig
    came back at 80k verts). The port needs u16 indices and a few-k-tri
    fighter, so simplify dense inputs with quadric collapse and remap
    attributes (uv, normal, skin weights) from the nearest original vert."""
    if len(pos) <= max_verts or len(tris) <= int(target_tris * 1.15):
        return pos, nrm, uv, tris, jix, wts
    try:
        import numpy as np
        import fast_simplification
    except ImportError as e:
        print(f"decimate: {len(pos)} verts but no simplifier available ({e})")
        return pos, nrm, uv, tris, jix, wts
    P = np.asarray(pos, np.float64); F = np.asarray(tris, np.int64)
    red = max(0.0, 1.0 - target_tris / max(1, len(F)))
    P2, F2, collapses = fast_simplification.simplify(P, F, target_reduction=red,
                                                     return_collapses=True)
    # attribute remap through the collapse history: each surviving vertex
    # takes uv/normal/weights from an original vertex that collapsed INTO
    # it (same UV island), never from a spatial neighbour on another island
    _, _, mapping = fast_simplification.replay_simplification(P, F, collapses)
    mapping = np.asarray(mapping)
    idx = np.full(len(P2), -1, np.int64)
    for i_orig in range(len(mapping) - 1, -1, -1):
        j = int(mapping[i_orig])
        if 0 <= j < len(P2):
            idx[j] = i_orig
    # any survivor without a recorded source falls back to nearest original
    if (idx < 0).any():
        from scipy.spatial import cKDTree
        _, near = cKDTree(P).query(P2[idx < 0])
        idx[idx < 0] = near
    pos2 = [tuple(map(float, p)) for p in P2]
    uv2 = [uv[i] for i in idx]
    nrm2 = [nrm[i] for i in idx] if nrm is not None else None
    jix2 = [list(jix[i]) for i in idx]
    wts2 = [list(wts[i]) for i in idx]
    tris2 = [tuple(int(k) for k in f) for f in F2]
    print(f"decimate: {len(pos)} verts / {len(tris)} tris -> {len(pos2)} / {len(tris2)}")
    return pos2, nrm2, uv2, tris2, jix2, wts2


TRIPO2MESHY = {
    "Root": "Hips", "Hip": "Hips", "Pelvis": "Hips",
    "Waist": "Spine", "Spine01": "Spine01", "Spine02": "Spine02",
    "NeckTwist01": "neck", "NeckTwist02": "neck", "Head": "Head",
    "L_Clavicle": "LeftShoulder", "R_Clavicle": "RightShoulder",
    "L_Upperarm": "LeftArm", "L_UpperarmTwist01": "LeftArm", "L_UpperarmTwist02": "LeftArm",
    "L_Forearm": "LeftForeArm", "L_ForearmTwist01": "LeftForeArm", "L_ForearmTwist02": "LeftForeArm",
    "L_Hand": "LeftHand",
    "R_Upperarm": "RightArm", "R_UpperarmTwist01": "RightArm", "R_UpperarmTwist02": "RightArm",
    "R_Forearm": "RightForeArm", "R_ForearmTwist01": "RightForeArm", "R_ForearmTwist02": "RightForeArm",
    "R_Hand": "RightHand",
    "L_Thigh": "LeftUpLeg", "L_ThighTwist01": "LeftUpLeg", "L_ThighTwist02": "LeftUpLeg",
    "L_Calf": "LeftLeg", "L_CalfTwist01": "LeftLeg", "L_CalfTwist02": "LeftLeg",
    "L_Foot": "LeftFoot", "L_ToeBase": "LeftToeBase",
    "R_Thigh": "RightUpLeg", "R_ThighTwist01": "RightUpLeg", "R_ThighTwist02": "RightUpLeg",
    "R_Calf": "RightLeg", "R_CalfTwist01": "RightLeg", "R_CalfTwist02": "RightLeg",
    "R_Foot": "RightFoot", "R_ToeBase": "RightToeBase",
}
# node whose rest position anchors each canonical joint
TRIPO_PRIMARY = {
    "Hips": "Pelvis", "Spine": "Waist", "Spine01": "Spine01",
    "Spine02": "Spine02", "neck": "NeckTwist01", "Head": "Head",
    "LeftShoulder": "L_Clavicle", "RightShoulder": "R_Clavicle",
    "LeftArm": "L_Upperarm", "LeftForeArm": "L_Forearm", "LeftHand": "L_Hand",
    "RightArm": "R_Upperarm", "RightForeArm": "R_Forearm", "RightHand": "R_Hand",
    "LeftUpLeg": "L_Thigh", "LeftLeg": "L_Calf",
    "LeftFoot": "L_Foot", "LeftToeBase": "L_ToeBase",
    "RightUpLeg": "R_Thigh", "RightLeg": "R_Calf",
    "RightFoot": "R_Foot", "RightToeBase": "R_ToeBase",
}


def tripo_to_meshy(pos, names, jpos, jix, wts):
    old_idx = {n: i for i, n in enumerate(names)}
    canon = []
    for c in TRIPO_PRIMARY:
        if TRIPO_PRIMARY[c] in old_idx:
            canon.append(c)
    new_names = canon + ["head_end"]
    new_idx = {n: i for i, n in enumerate(new_names)}
    new_jpos = [list(jpos[old_idx[TRIPO_PRIMARY[c]]]) for c in canon]
    # synth head_end above the head at the mesh top
    ymax = max(p[1] for p in pos)
    h = list(new_jpos[new_idx["Head"]])
    new_jpos.append([h[0], ymax, h[2]])

    old2new = {}
    for i, n in enumerate(names):
        c = TRIPO2MESHY.get(n)
        old2new[i] = new_idx.get(c, new_idx["Hips"])

    new_jix, new_wts = [], []
    for ji, wt in zip(jix, wts):
        acc = {}
        for k in range(4):
            if wt[k] <= 0.0:
                continue
            j = old2new[ji[k]]
            acc[j] = acc.get(j, 0.0) + wt[k]
        top = sorted(acc.items(), key=lambda kv: -kv[1])[:4]
        ji2 = [0, 0, 0, 0]
        wt2 = [0.0, 0.0, 0.0, 0.0]
        for k, (j, w) in enumerate(top):
            ji2[k] = j
            wt2[k] = w
        new_jix.append(ji2)
        new_wts.append(wt2)
    print(f"tripo rig folded: {len(names)} joints -> {len(new_names)} canonical")
    return new_names, new_jpos, new_jix, new_wts


def load_autoskin(path):
    """Load an UNRIGGED Meshy GLB and skin it procedurally (auto_skin.py).
    Replaces the Meshy rigging stage: deterministic seams, guaranteed
    symmetry, band-limited weights."""
    gltf, bin_ = load_glb(path)
    prim = gltf["meshes"][0]["primitives"][0]
    pos = read_accessor(gltf, bin_, prim["attributes"]["POSITION"])
    uv = read_accessor(gltf, bin_, prim["attributes"]["TEXCOORD_0"])
    idx = [t[0] for t in read_accessor(gltf, bin_, prim["indices"])]
    tris = [(idx[i], idx[i+1], idx[i+2]) for i in range(0, len(idx), 3)]

    img = None
    if gltf.get("images"):
        # resolve the BASE COLOR image through the material — multi-texture
        # exports (Tripo: NormalGL + Color + ORM) put the normal map first
        img_idx = 0
        mats = gltf.get("materials") or []
        if mats:
            bct = (mats[0].get("pbrMetallicRoughness") or {}).get("baseColorTexture")
            if bct is not None:
                img_idx = gltf["textures"][bct["index"]].get("source", 0)
        bv = gltf["bufferViews"][gltf["images"][img_idx]["bufferView"]]
        start = bv.get("byteOffset", 0)
        img = Image.open(io.BytesIO(bin_[start:start+bv["byteLength"]])).convert("RGB")

    # smooth welded normals (same rationale as load_rigged)
    key2group = {}
    for i, p in enumerate(pos):
        key = (round(p[0], 5), round(p[1], 5), round(p[2], 5))
        key2group.setdefault(key, []).append(i)
    acc = [[0.0, 0.0, 0.0] for _ in pos]
    for a, b, c in tris:
        pa, pb, pc = pos[a], pos[b], pos[c]
        u = [pb[k]-pa[k] for k in range(3)]
        w = [pc[k]-pa[k] for k in range(3)]
        fn = [u[1]*w[2]-u[2]*w[1], u[2]*w[0]-u[0]*w[2], u[0]*w[1]-u[1]*w[0]]
        for i in (a, b, c):
            for k in range(3):
                acc[i][k] += fn[k]
    nrm = [None] * len(pos)
    for group in key2group.values():
        s = [0.0, 0.0, 0.0]
        for i in group:
            for k in range(3):
                s[k] += acc[i][k]
        ln = math.sqrt(sum(c*c for c in s)) or 1e-9
        sn = [c/ln for c in s]
        for i in group:
            nrm[i] = sn

    import auto_skin
    names, jpos, jix, wts = auto_skin.skin(pos, tris)
    print(f"auto-skin: {len(pos)} verts, skeleton "
          f"H={max(p[1] for p in pos)-min(p[1] for p in pos):.2f}")
    return pos, nrm, uv, tris, img, jix, wts, names, jpos


# --------------------------------------------------- meshy -> mario mapping
# Mario part joints and their bone-defining child joints (spawn frames).
# Meshy bone name -> (mario part joint, mario bone child joint or None).
# Side X/Y placeholders resolved by mesh-side sign so game handedness
# matches v8's proven convention (mesh +x chain -> joints 8/9/10, 19/20/22).
def build_bone_map(names, jpos, posx, negx):
    # posx/negx come from main's facing-corrected side pick — the ONE
    # source of truth. (An independent x-coordinate pick here silently
    # mirrored weights against the conform when main's facing fix
    # swapped sides.)
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
# skeleton adjacency of canonical parts: the post-claim re-smoothing may
# only blend a vert toward parts adjacent to ones it already carries
# (head<->chest at the neck, chest<->shoulder at the collar). Without
# this the 4-hop diffusion walks arm weight through the collar into the
# face on short-necked meshes, and every arm swing drags the face.
PART_ADJ = {6: {8, 12, 14, 19, 24}, 8: {6, 9}, 9: {8, 10}, 10: {9},
            12: {6}, 14: {6, 15}, 15: {14, 16}, 16: {15},
            19: {6, 20}, 20: {19, 22}, 22: {20},
            24: {6, 25}, 25: {24, 27}, 27: {25}}
# anchor joints for inherited parts: (mesh node name resolved per side,
# mario joint)  e.g. hand part anchors mesh Hand node onto mario joint 10.


TARGET_MAP = None
TARGET_PARTS_JSON = None
TARGET_BLANK_EXTRA = []
TARGET_SNAP_ACCS = []
TARGET_KEEP_VANILLA = []
TARGET_SWAP_SIDES = False
TARGET_CONFORM = None
TARGET_TUNE = {}


def main():
    argv = sys.argv[1:]
    global TARGET_MAP, TARGET_PARTS_JSON, TARGET_BLANK_EXTRA, TARGET_SNAP_ACCS, TARGET_KEEP_VANILLA, TARGET_SWAP_SIDES, TARGET_CONFORM, TARGET_TUNE
    if "--target" in argv:
        ti = argv.index("--target")
        _prof = json.load(open(argv[ti + 1]))
        TARGET_MAP = {int(k): int(v) for k, v in _prof["map"].items()}
        TARGET_PARTS_JSON = _prof.get("parts")
        TARGET_BLANK_EXTRA = [int(j) for j in _prof.get("blank_extra", [])]
        TARGET_SNAP_ACCS = [int(j) for j in _prof.get("snap_accessories", [])]
        TARGET_KEEP_VANILLA = [int(j) for j in _prof.get("keep_vanilla", [])]
        TARGET_SWAP_SIDES = bool(_prof.get("swap_sides", False))
        TARGET_CONFORM = _prof.get("conform")
        TARGET_TUNE = _prof.get("tune", {})
        if "--base-recipe" in sys.argv:
            # A/B baseline: pre-2026-08-28 recipe — no profile tunes
            # (rigid_arms/arm_anchor/head_recenter/widen_*), no provider
            # claim, flat part claim
            TARGET_TUNE = {k: v for k, v in TARGET_TUNE.items()
                           if k in ("postsmooth_iters", "rigid_legs", "perp_boost")}
            print("base recipe: session tunes and claims disabled")
        argv = argv[:ti] + argv[ti + 2:]
        print(f"target skeleton: {_prof.get('name', '?')} "
              f"({len(TARGET_MAP)} canonical parts mapped)")
    if "--project-source" in argv:
        pi = argv.index("--project-source")
        project_source_path = argv[pi + 1]
        argv = argv[:pi] + argv[pi + 2:]
    else:
        project_source_path = None
    args = [a for a in argv if a not in ("--autoskin", "--reskin", "--mild-color", "--redchest", "--bluelegs", "--brownhair", "--capfix", "--vanillaflat", "--flatten", "--debleed", "--no-profile", "--no-smooth-disp", "--smooth-disp", "--no-smooth-weights", "--no-postsmooth", "--adjguard", "--flip-facing", "--sharpen", "--rigid", "--no-symlimbs", "--no-symweights", "--guidedflat", "--binflat", "--claim-freeze", "--graded-armclaim", "--flat-armclaim", "--base-recipe")]
    # (--target consumed above with its argument)
    autoskin = "--autoskin" in sys.argv
    glb_path, frames_path, out_path = args[0], args[1], args[2]
    loader = load_autoskin if autoskin else load_rigged
    pos, nrm, uv, tris, img, jix, wts, names, jpos = loader(glb_path)
    # ---- chain joint repair (general): auto-riggers drop the knee (or
    # elbow) at the ankle/wrist when clothing hides it, leaving a near-
    # zero segment. The retarget needs each bone's distal end to land on
    # the next joint, so a degenerate segment either explodes the scale
    # or (if clamped) tears the limb. Relocate the middle joint to mid-
    # chain and reweight that chain's verts along the repaired polyline.
    _nidx = {n: i for i, n in enumerate(names)}
    _ysR = [p[1] for p in pos]; _HR = max(_ysR) - min(_ysR)
    jpos = [list(j) for j in jpos]
    jix = [list(j) for j in jix]; wts = [list(w) for w in wts]
    for _side in ("Left", "Right"):
        for (_pa, _mid, _dist) in ((_side+"UpLeg", _side+"Leg", _side+"Foot"),
                                   (_side+"Arm", _side+"ForeArm", _side+"Hand")):
            if not all(n in _nidx for n in (_pa, _mid, _dist)):
                continue
            ia, im_, idd = _nidx[_pa], _nidx[_mid], _nidx[_dist]
            A_, M_, D_ = jpos[ia], jpos[im_], jpos[idd]
            l1 = math.dist(A_, M_); l2 = math.dist(M_, D_)
            if l2 >= 0.4 * l1 and l1 >= 0.4 * l2:
                continue
            newM = [A_[k] + 0.5 * (D_[k] - A_[k]) for k in range(3)]
            jpos[im_] = newM
            print(f"joint repair: {_mid} moved to mid-chain (segments were "
                  f"{l1/_HR*100:.1f}% / {l2/_HR*100:.1f}% of height)")
            # reweight verts along the chain polyline A -> D
            ax = [D_[k] - A_[k] for k in range(3)]
            al2 = sum(c*c for c in ax) or 1e-9
            n_rw = 0
            for vi in range(len(pos)):
                slots = {jix[vi][k]: k for k in range(4) if wts[vi][k] > 0}
                if ia not in slots and im_ not in slots:
                    continue
                mass = sum(wts[vi][k] for b, k in slots.items() if b in (ia, im_))
                u = sum((pos[vi][k] - A_[k]) * ax[k] for k in range(3)) / al2
                # blend band around the new middle joint (u = 0.5)
                t = min(1.0, max(0.0, (u - 0.42) / 0.16))
                t = t * t * (3 - 2 * t)
                w_mid = mass * t; w_pa = mass * (1 - t)
                # write back: reuse existing slots, else take the weakest
                for bone, wv in ((ia, w_pa), (im_, w_mid)):
                    if bone in slots:
                        wts[vi][slots[bone]] = wv
                    else:
                        kmin = min(range(4), key=lambda k: wts[vi][k])
                        jix[vi][kmin] = bone; wts[vi][kmin] = wv
                        slots[bone] = kmin
                n_rw += 1
            print(f"chain reweight: {n_rw} verts redistributed along {_pa}->{_dist}")

    # ---- anatomical influence clamp (general): auto-riggers let thigh
    # bones drive belly verts and upper-arm bones drive chest verts past
    # the shoulder. Under a strong stance rotation those leaked weights
    # stretch the torso. Verts above the hip joints lose leg-bone weight
    # (-> Hips); verts medial of a shoulder joint lose that arm's weight
    # (-> Spine02 / nearest torso bone).
    _nI = {n: i for i, n in enumerate(names)}
    _upI = [jpos[_nI["neck"]][k] - jpos[_nI["Hips"]][k] for k in range(3)] if "neck" in _nI and "Hips" in _nI else [0, 1, 0]
    _upL = math.sqrt(sum(c*c for c in _upI)) or 1e-9
    _upI = [c / _upL for c in _upI]
    _torso_fallback = _nI.get("Spine02", _nI.get("Spine01", _nI.get("Spine", _nI.get("Hips"))))
    n_clamp = 0
    if "Hips" in _nI and _torso_fallback is not None:
        _legb = {}
        for _s in ("Left", "Right"):
            for _b in ("UpLeg", "Leg", "Foot", "ToeBase"):
                if _s + _b in _nI: _legb[_nI[_s + _b]] = _nI.get(_s + "UpLeg")
        _armb = {}
        for _s in ("Left", "Right"):
            if _s + "Arm" in _nI and _s + "Shoulder" in _nI:
                for _b in ("Arm", "ForeArm", "Hand"):
                    if _s + _b in _nI: _armb[_nI[_s + _b]] = _nI[_s + "Shoulder"]
        for vi in range(len(pos)):
            p = pos[vi]
            h_up = sum((p[k] - 0) * _upI[k] for k in range(3))
            changed = False
            for k in range(4):
                b = jix[vi][k]; w = wts[vi][k]
                if w <= 0: continue
                if b in _legb and _legb[b] is not None:
                    hip = jpos[_legb[b]]
                    if h_up > sum(hip[j] * _upI[j] for j in range(3)) + 0.02 * _upL:
                        jix[vi][k] = _nI["Hips"]; changed = True
                elif b in _armb:
                    sh = jpos[_armb[b]]
                    # lateral direction from torso center to this shoulder
                    ctr = jpos[_torso_fallback]
                    lat = [sh[j] - ctr[j] for j in range(3)]
                    ll = math.sqrt(sum(c*c for c in lat)) or 1e-9
                    lat = [c / ll for c in lat]
                    if sum((p[j] - sh[j]) * lat[j] for j in range(3)) < -0.03 * _upL:
                        jix[vi][k] = _torso_fallback; changed = True
            if changed:
                # merge duplicate bones
                acc = {}
                for k in range(4):
                    if wts[vi][k] > 0: acc[jix[vi][k]] = acc.get(jix[vi][k], 0.0) + wts[vi][k]
                items = sorted(acc.items(), key=lambda kv: -kv[1])[:4]
                jix[vi] = [b for b, _ in items] + [items[0][0]] * (4 - len(items))
                wts[vi] = [w for _, w in items] + [0.0] * (4 - len(items))
                n_clamp += 1
    if n_clamp:
        print(f"influence clamp: {n_clamp} verts lost anatomically-impossible limb weights")

    # ---- weight sharpening (general, default): vanilla fighters are RIGID
    # parts; provider skin weights spread each bone's influence over a
    # wide band, which flattens limbs into wedges in sharp bends (taunt,
    # smashes). Keep each vertex rigid to its dominant bone and blend only
    # inside a narrow geometric band around each joint, toward the bone's
    # hierarchy neighbour on that side. Deterministic, provider-independent.
    if "--sharpen" in sys.argv:   # experimental: rigid-to-bone weights with narrow joint bands (opt-in)
        _nS = {n: i for i, n in enumerate(names)}
        _parent = {}
        for _side in ("Left", "Right"):
            for a_, b_ in (("Spine02", _side+"Shoulder"), (_side+"Shoulder", _side+"Arm"), (_side+"Arm", _side+"ForeArm"),
                           (_side+"ForeArm", _side+"Hand"), ("Hips", _side+"UpLeg"), (_side+"UpLeg", _side+"Leg"),
                           (_side+"Leg", _side+"Foot"), (_side+"Foot", _side+"ToeBase")):
                if a_ in _nS and b_ in _nS: _parent[_nS[b_]] = _nS[a_]
        for a_, b_ in (("Hips", "Spine"), ("Spine", "Spine01"), ("Spine01", "Spine02"), ("Spine02", "neck"), ("neck", "Head"), ("Head", "head_end")):
            if a_ in _nS and b_ in _nS: _parent[_nS[b_]] = _nS[a_]
        _children = {}
        for c_, p_ in _parent.items(): _children.setdefault(p_, []).append(c_)
        _ysS = [p[1] for p in pos]; _HS = max(_ysS) - min(_ysS)
        BAND = 0.045 * _HS          # half-width of the blend band at a joint
        def _proj(pt, a_, b_):
            ab = [b_[k]-a_[k] for k in range(3)]; L2 = sum(c*c for c in ab) or 1e-9
            return sum((pt[k]-a_[k])*ab[k] for k in range(3)) / L2
        n_sharp = 0
        for vi in range(len(pos)):
            kd = max(range(4), key=lambda k: wts[vi][k]); b = jix[vi][kd]
            if wts[vi][kd] <= 0: continue
            v = pos[vi]
            # candidate joints: this bone's root (blend toward parent) and
            # each child's root (blend toward that child)
            best = None   # (weight_other, other_bone)
            if b in _parent:
                jroot = jpos[b]; par = _parent[b]
                # distance along the bone from its root; negative = past root toward parent
                ref = jpos[_children[b][0]] if b in _children and _children[b] else None
                if ref is not None:
                    t = _proj(v, jroot, ref) * math.dist(jroot, ref)
                else:
                    t = math.dist(v, jroot)
                if t < BAND:
                    w_par = 0.5 * (1.0 - max(-1.0, min(1.0, t / BAND)))
                    best = (w_par, par)
            for ch in _children.get(b, []):
                jc = jpos[ch]
                cref = jpos[_children[ch][0]] if ch in _children and _children[ch] else None
                if cref is not None:
                    t = _proj(v, jc, cref) * math.dist(jc, cref)   # >0 = past the child joint into the child bone
                else:
                    t = -math.dist(v, jc)
                if t > -BAND:
                    w_ch = 0.5 * (1.0 + max(-1.0, min(1.0, t / BAND)))
                    if best is None or w_ch > best[0]:
                        best = (w_ch, ch)
            if best is None or best[0] <= 0.0:
                jix[vi] = [b, b, b, b]; wts[vi] = [1.0, 0.0, 0.0, 0.0]
            else:
                w_o = min(0.5, best[0])   # never let the neighbour dominate this side of the joint
                jix[vi] = [b, best[1], b, b]; wts[vi] = [1.0 - w_o, w_o, 0.0, 0.0]
            n_sharp += 1
        print(f"weight sharpening: {n_sharp} verts rigid-to-bone with {BAND/_HS*100:.1f}%H joint blend bands")

    # ---- provider bone-weight smoothing (general): hard per-bone weight
    # boundaries between bones whose retarget maps disagree tear the mesh
    # at spawn. Diffuse the PROVIDER weights over the position-welded
    # mesh graph (top-4 kept) so disagreeing maps blend over a band —
    # every bone's rotation is preserved, unlike smoothing positions.
    if "--no-smooth-weights" not in sys.argv and "--sharpen" not in sys.argv:
        _wk2 = {}
        for _i, _p in enumerate(pos):
            _wk2.setdefault((round(_p[0], 3), round(_p[1], 3), round(_p[2], 3)), []).append(_i)
        _rep2 = {}
        for _g in _wk2.values():
            for _i in _g: _rep2[_i] = _g[0]
        _adj2 = {}
        for _a, _b2, _c in tris:
            _ra, _rb, _rc = _rep2[_a], _rep2[_b2], _rep2[_c]
            for _x, _y in ((_ra, _rb), (_ra, _rc), (_rb, _rc)):
                if _x != _y:
                    _adj2.setdefault(_x, set()).add(_y); _adj2.setdefault(_y, set()).add(_x)
        _cur2 = {}
        for r in _adj2:
            d = {}
            for k in range(4):
                if wts[r][k] > 0:
                    d[jix[r][k]] = d.get(jix[r][k], 0.0) + wts[r][k]
            _cur2[r] = d
        # 16 iters (was 3): the 3-iter band was too narrow to bridge the
        # torso/leg retarget disagreement at the waist — the ragged
        # dominance boundary printed straight through the texture as a
        # zigzag hem tear on every conversion.
        for _it in range(int(os.environ.get("OSB_WSMOOTH_ITERS", "16"))):
            _nxt2 = {}
            for r, nbrs in _adj2.items():
                acc = {b: 0.5 * w for b, w in _cur2[r].items()}
                share = 0.5 / len(nbrs)
                for nb in nbrs:
                    for b, w in _cur2[nb].items():
                        acc[b] = acc.get(b, 0.0) + share * w
                top = sorted(acc.items(), key=lambda kv: -kv[1])[:4]
                tot = sum(w for _, w in top) or 1.0
                _nxt2[r] = {b: w / tot for b, w in top if w / tot > 0.02}
            _cur2 = _nxt2
        for _i in range(len(pos)):
            r = _rep2[_i]
            if r in _cur2 and _cur2[r]:
                items = sorted(_cur2[r].items(), key=lambda kv: -kv[1])
                ji = [b for b, _ in items] + [items[0][0]] * (4 - len(items))
                ww = [w for _, w in items] + [0.0] * (4 - len(items))
                jix[_i] = ji; wts[_i] = ww
        print(f"weight smoothing: provider bone weights diffused {int(os.environ.get('OSB_WSMOOTH_ITERS', '16'))} iters")

    if "--reskin" in sys.argv and not autoskin:
        # keep the Meshy skeleton (joint placement is good) but replace
        # its spilly weights with band-limited capsule weights
        import auto_skin
        jix, wts = auto_skin.reskin(pos, tris, names, jpos, jix, wts)
        print("reskin: disciplined weights on the Meshy skeleton")

    # ---- symmetrize provider weights. Auto-rig weights are ~7% asymmetric
    # between mirror-partner verts on a symmetric mesh (measured on Tripo
    # rigs), which poses the two sides differently in every animation.
    # Mirror-average each vert's weights with its geometric mirror
    # partner's (Left<->Right joints swapped). Guarded per vert: only when
    # a partner exists within 3% of mesh height, so genuinely asymmetric
    # features (a side ponytail, one glove) keep their own weights.
    if "--no-symweights" not in sys.argv and \
            "LeftArm" in names and "RightArm" in names:
        import numpy as _nsw
        from scipy.spatial import cKDTree as _KD
        _P = _nsw.array(pos)
        _la, _ra = jpos[names.index("LeftArm")], jpos[names.index("RightArm")]
        _ax = max(range(3), key=lambda k: abs(_la[k] - _ra[k]))
        _mid = (_la[_ax] + _ra[_ax]) / 2.0
        _mirP = _P.copy()
        _mirP[:, _ax] = 2 * _mid - _mirP[:, _ax]
        _d, _pi = _KD(_P).query(_mirP)
        _hgt = float(_P[:, 1].max() - _P[:, 1].min()) or 1.0
        _swp = {}
        for _i2, _nm in enumerate(names):
            _o = ("Right" + _nm[4:]) if _nm.startswith("Left") else \
                 (("Left" + _nm[5:]) if _nm.startswith("Right") else _nm)
            _swp[_i2] = names.index(_o) if _o in names else _i2
        _nj, _nw = [], []
        _nblend = 0
        for _v in range(len(pos)):
            if _d[_v] > 0.03 * _hgt:
                _nj.append(jix[_v]); _nw.append(wts[_v])
                continue
            _m = _pi[_v]
            _acc = {}
            for _k in range(4):
                _acc[jix[_v][_k]] = _acc.get(jix[_v][_k], 0.0) + 0.5*wts[_v][_k]
            for _k in range(4):
                _sj = _swp[jix[_m][_k]]
                _acc[_sj] = _acc.get(_sj, 0.0) + 0.5*wts[_m][_k]
            _it = sorted(_acc.items(), key=lambda kv: -kv[1])[:4]
            _tt = sum(w for _, w in _it) or 1.0
            _nj.append([b for b, _ in _it] + [_it[0][0]]*(4-len(_it)))
            _nw.append([w/_tt for _, w in _it] + [0.0]*(4-len(_it)))
            _nblend += 1
        jix, wts = _nj, _nw
        print(f"symweights: mirror-averaged provider weights on "
              f"{_nblend}/{len(pos)} verts")

    # ---- PROVIDER arm claim (pre-bake): the authored bind shape comes
    # from lbs() over the PROVIDER bone weights, so the part-level arm
    # claim (further down) can only fix runtime deformation — a sleeve
    # rigged to Shoulder/Spine still BAKES hugging the chest conform,
    # never gaining the arm's stretch-widening, and reads as a skinny
    # bolt-on tube when the target's arm bones are long (samus 2.7x).
    # Re-lean the provider weights of capsule sleeve verts onto the arm
    # bones HERE, before the bake, with the same graded falloff; the
    # part weights derived from these inherit the claim automatically.
    if not ({"--flat-armclaim", "--base-recipe"} & set(sys.argv)) \
            and TARGET_TUNE.get("rigid_arms"):
        # rigid-arm targets ONLY: the pre-bake re-lean exists so the rigid
        # assembly owns its sleeve in the BAKE. On articulated targets it
        # re-bakes garment geometry and carves visible tears (2026-08-29
        # blind sweep: mario base won 6/6 — waist gashes on rohan/queen).
        _nI = {n: i for i, n in enumerate(names)}
        _torso_b = {i for n, i in _nI.items()
                    if n in ("Hips", "Spine", "Spine01", "Spine02", "neck")
                    or "Shoulder" in n}
        n_pclaim = 0
        for _side in ("Left", "Right"):
            for _s0, _s1 in ((_side + "Arm", _side + "ForeArm"),
                             (_side + "ForeArm", _side + "Hand")):
                if _s0 not in _nI or _s1 not in _nI:
                    continue
                _ai = _nI[_s0]
                _a = jpos[_ai]
                _b = jpos[_nI[_s1]]
                _ab = [_b[k] - _a[k] for k in range(3)]
                _ab2 = sum(c * c for c in _ab) or 1e-9
                _blen = _ab2 ** 0.5
                _u = [c / _blen for c in _ab]
                _ctr = jpos[_nI["Spine02"]] if "Spine02" in _nI else _a
                _shlat = sum((_a[k] - _ctr[k]) * _u[k] for k in range(3))
                _r2 = (2.4 * _blen) ** 2
                for i in range(len(pos)):
                    _lat = sum((pos[i][k] - _ctr[k]) * _u[k] for k in range(3))
                    if _lat < 0.6 * _shlat:
                        continue
                    _t = sum((pos[i][k] - _a[k]) * _ab[k] for k in range(3)) / _ab2
                    if _t < -0.1 or _t > 1.1:
                        continue
                    _dom = jix[i][max(range(4), key=lambda k: wts[i][k])]
                    _hd = names[_dom] in ("Head", "head_end", "headfront")
                    if _dom not in _torso_b and not _hd and \
                       not names[_dom].startswith(_side):
                        continue   # other side's geometry passing through
                    _q = [_a[k] + max(0.0, min(1.0, _t)) * _ab[k]
                          for k in range(3)]
                    _d2 = sum((pos[i][k] - _q[k]) ** 2 for k in range(3))
                    if _d2 > ((0.72 * _blen) ** 2 if _hd else _r2):
                        continue
                    # rigid_arms: the arm is ONE rigid assembly — a graded
                    # falloff just leaves the sleeve's shoulder end riding
                    # the chest, squeezing the tube into a flap when the
                    # shoulder swings. Claim near-totally instead.
                    _g = 0.95 if TARGET_TUNE.get("rigid_arms") else \
                        0.45 + 0.5 * max(0.0, min(1.0, _t))
                    _mix = {}
                    for _k in range(4):
                        if wts[i][_k] > 0:
                            _mix[jix[i][_k]] = _mix.get(jix[i][_k], 0.0) \
                                + (1.0 - _g) * wts[i][_k]
                    _mix[_ai] = _mix.get(_ai, 0.0) + _g
                    _top = sorted(_mix.items(), key=lambda kv: -kv[1])[:4]
                    _tt = sum(w for _, w in _top) or 1.0
                    jix[i] = [j for j, _ in _top] + [0] * (4 - len(_top))
                    wts[i] = [w / _tt for _, w in _top] + [0.0] * (4 - len(_top))
                    n_pclaim += 1
        if n_pclaim:
            print(f"provider arm claim (pre-bake): {n_pclaim} sleeve verts "
                  f"re-leaned onto arm bones")

    frames = load_frames(frames_path)
    if TARGET_MAP is not None:
        # the skel dump is keyed by the TARGET fighter's joint ids; the
        # converter reasons in canonical (Mario) part ids throughout, so
        # remap here and translate back when the bundle is written.
        frames = {c: frames[t] for c, t in TARGET_MAP.items() if t in frames}

    # ---- symmetrize the limb bind pose. The vanilla rest pose is NOT
    # mirror-symmetric (one arm tucked across the chest, one out; legs
    # likewise), and everything downstream — triad twist-ref choice,
    # bone scales, conform, weights, claims — runs in this pose, so the
    # two sides of a symmetric mesh got measurably different treatment
    # baked into the bundle (boyang: ~14 units mean mirror error on the
    # arms vs ~0 in the source GLB). The bind pose is author-chosen (the
    # engine skins via the embedded BIND section, frame x inv(bind)), so
    # replace each -side limb chain's frames with the exact mirror of the
    # +side chain across the character's sagittal plane. Vanilla left and
    # right part geometry mirrors under a local z flip (verified on all
    # six pairs), so the mirrored frame is sigma . R . S_world.
    if "--no-symlimbs" not in sys.argv and all(
            j in frames for j in (6, 11, 8, 9, 10, 14, 15, 16,
                                  19, 20, 21, 22, 24, 25, 26, 27)):
        _c6 = list(frames[6][0])
        _upv = normalize([frames[11][0][k] - frames[6][0][k] for k in range(3)])
        _latv = [frames[8][0][k] - frames[14][0][k] for k in range(3)]
        _latv = [_latv[k] - _upv[k]*sum(_latv[j]*_upv[j] for j in range(3))
                 for k in range(3)]
        _n = normalize(_latv)
        def _reflect_pt(p):
            d = sum((p[k]-_c6[k])*_n[k] for k in range(3))
            return [p[k] - 2*d*_n[k] for k in range(3)]
        _Sw = [[(1.0 if r == c else 0.0) - 2*_n[r]*_n[c] for c in range(3)]
               for r in range(3)]
        _sig = [1.0, 1.0, -1.0]        # vanilla local left/right mirror
        for _p, _q in ((8, 14), (9, 15), (10, 16),
                       (19, 24), (20, 25), (21, 26), (22, 27)):
            _op, _Rp = frames[_p]
            _Rq = [[_sig[r]*sum(_Rp[r][k]*_Sw[k][c] for k in range(3))
                    for c in range(3)] for r in range(3)]
            frames[_q] = (_reflect_pt(_op), _Rq)
        # midline joints should sit ON the sagittal plane — the head joint
        # is a few units off it in the crumpled rest pose, which anchors
        # the whole head part off-center
        for _mj in (11, 12):
            if _mj in frames:
                _om, _Rm = frames[_mj]
                _dm = sum((_om[k]-_c6[k])*_n[k] for k in range(3))
                frames[_mj] = ([_om[k] - _dm*_n[k] for k in range(3)], _Rm)
        print("symlimbs: -side limb bind frames mirrored from +side "
              "(symmetric conform pose)")
    name_idx = {n: i for i, n in enumerate(names)}

    posx = "Left" if jpos[name_idx["LeftArm"]][0] > jpos[name_idx["RightArm"]][0] else "Right"
    negx = "Right" if posx == "Left" else "Left"
    # facing disambiguation (general): the posx pick above is decided by
    # noise when the arms spread along z. Toes point FORWARD on any
    # humanoid: require dot(toe_dir, lat x up) > 0, else swap sides
    # (which flips the retarget's forward triad 180).
    def _v(a, b): return [a[k]-b[k] for k in range(3)]
    _up = _v(jpos[name_idx["neck"]], jpos[name_idx["Hips"]])
    _lat = _v(jpos[name_idx[posx+"Arm"]], jpos[name_idx[negx+"Arm"]])
    _fwd = [_lat[1]*_up[2]-_lat[2]*_up[1], _lat[2]*_up[0]-_lat[0]*_up[2],
            _lat[0]*_up[1]-_lat[1]*_up[0]]
    _feet_j = [i for i, n in enumerate(names) if "Foot" in n]
    if _feet_j:
        _ank = [sum(jpos[i][k] for i in _feet_j)/len(_feet_j) for k in range(3)]
        _upl = math.sqrt(sum(c*c for c in _up)) or 1e-9
        _upn = [c/_upl for c in _up]
        # toe cue: project each foot's verts onto the forward AXIS
        # (lat x up; only the SIGN is unknown) relative to that foot's own
        # ankle, and compare 95th-percentile reach forward vs backward —
        # toes reach 2-3x farther than heels on any footwear. A single
        # farthest-vertex pick is defeated once in a while by sandal
        # soles / pant cuffs weighted onto the foot (Joey Flynn's head
        # rendered backwards); reach asymmetry with an ambiguity band is
        # not.
        _fwl = math.sqrt(sum(c*c for c in _fwd)) or 1e-9
        _fwn = [c/_fwl for c in _fwd]
        _projs = []
        for vi in range(len(pos)):
            jb = jix[vi][max(range(4), key=lambda k: wts[vi][k])]
            if jb in _feet_j:
                _aj = jpos[jb]
                off = [pos[vi][k] - _aj[k] for k in range(3)]
                dv = sum(off[k]*_upn[k] for k in range(3))
                _projs.append(sum((off[k] - dv*_upn[k])*_fwn[k] for k in range(3)))
        _toe_h = None
        _nt = len(_projs)
        if _nt >= 16:
            _projs.sort()
            _fr = max(0.0, _projs[min(_nt - 1, int(_nt * 0.95))])
            _br = max(0.0, -_projs[max(0, int(_nt * 0.05))])
            _lo, _hi = min(_fr, _br), max(_fr, _br)
            if _hi > 1e-9 and (_lo < 1e-9 or _hi / max(_lo, 1e-9) >= 1.25):
                _toe_h = [(1.0 if _fr >= _br else -1.0) * c for c in _fwn]
                print(f"facing: toe cue reach fwd={_fr:.3f} back={_br:.3f} "
                      f"({'keep' if _fr >= _br else 'flip'} candidate)")
            else:
                print(f"facing: toe cue ambiguous (fwd={_fr:.3f} back={_br:.3f})")
        # face/head cues need no foot verts — gating them on _nt let a
        # character whose shoes are weighted to the calves (obama: zero
        # foot-dominant verts) skip EVERY cue and ship facing decided by
        # the arm-x noise pick (walked backwards in game).
        if True:
            _head_h = None
            if "Head" in name_idx:
                # head centroid offset: face + nose pull the head's mass
                # forward of the neck axis (big back hair can defeat it)
                _hj = jpos[name_idx["Head"]]
                _hv = [p for p in pos if p[1] > _hj[1]]
                if _hv:
                    _hc = [sum(p[k] for p in _hv)/len(_hv) for k in range(3)]
                    _off = [_hc[k] - _hj[k] for k in range(3)]
                    _dv2 = sum(_off[k]*_upn[k] for k in range(3))
                    _head_h = [_off[k] - _dv2*_upn[k] for k in range(3)]
            # PRIMARY cue: the face. Skin-coloured texels on the head
            # cluster on the front (hair/hats are not skin); their
            # horizontal offset from the head joint points forward. Works
            # for any human character. Ground truth from the roster: the
            # cue's DIRECTION was correct down to 1.6% H offset (bearded,
            # glasses-wearing characters just have less visible skin), so
            # only near-zero offsets are treated as noise — the old 4%
            # gate is what let a bad toe read flip Joey Flynn's facing.
            _face_h = None
            _ys_f = [p[1] for p in pos]
            _Hf = max(_ys_f) - min(_ys_f)
            if img is None or "Head" not in name_idx or "neck" not in name_idx:
                print(f"facing: face cue unavailable (img={'yes' if img is not None else 'no'}, "
                      f"Head={'yes' if 'Head' in name_idx else 'no'}, neck={'yes' if 'neck' in name_idx else 'no'})")
            if img is not None and "Head" in name_idx and "neck" in name_idx:
                try:
                    import numpy as _npf2
                    _hsvF = _npf2.asarray(img.convert("HSV"), _npf2.int16)
                    _W0, _H0 = img.size
                    _hj = jpos[name_idx["Head"]]; _ny = jpos[name_idx["neck"]][1]
                    _acc = [0.0, 0.0, 0.0]; _nsk = 0
                    for vi in range(len(pos)):
                        if pos[vi][1] <= _ny:
                            continue
                        _u, _v = uv[vi]
                        _x = min(_W0-1, max(0, int(_u*_W0))); _y = min(_H0-1, max(0, int(_v*_H0)))
                        _h, _s_, _vv = _hsvF[_y, _x]
                        if 3 <= _h <= 30 and 35 <= _s_ <= 190 and _vv >= 110:
                            for k in range(3): _acc[k] += pos[vi][k] - _hj[k]
                            _nsk += 1
                    if _nsk >= 120:
                        _acc = [c/_nsk for c in _acc]
                        _dv3 = sum(_acc[k]*_upn[k] for k in range(3))
                        _face_h = [_acc[k] - _dv3*_upn[k] for k in range(3)]
                        _fm = math.sqrt(sum(c*c for c in _face_h))
                        _fvote = 'flip' if sum(_face_h[k]*_fwd[k] for k in range(3)) < 0 else 'keep'
                        if _fm < 0.01 * _Hf:   # near-zero offset: direction is noise
                            print(f"facing: face cue weak ({_nsk} skin verts, |offset| {_fm/_Hf*100:.1f}% H, votes {_fvote}) — ignored")
                            _face_h = None
                        else:
                            print(f"facing: face cue from {_nsk} skin verts (|offset| {_fm/_Hf*100:.1f}% H, votes {_fvote})")
                    else:
                        print(f"facing: face cue insufficient ({_nsk} skin verts above neck)")
                except Exception as _e:
                    print(f"facing: face cue errored ({_e!r})")
                    _face_h = None
            if _face_h is not None:
                _flip = sum(_face_h[k]*_fwd[k] for k in range(3)) < 0
            elif _head_h is not None:
                _flip = sum(_head_h[k]*_fwd[k] for k in range(3)) < 0
                print(f"facing: no face cue — head-offset decides ({'flip' if _flip else 'keep'})")
            elif _toe_h is not None:
                _flip = sum(_toe_h[k]*_fwd[k] for k in range(3)) < 0
                print(f"facing: no face/head cue — toe reach decides ({'flip' if _flip else 'keep'})")
            else:
                _flip = False
            if "--flip-facing" in sys.argv:
                _flip = not _flip   # manual override when every cue misreads
            if _flip:
                posx, negx = negx, posx
                print(f"facing fix: forward cue opposes fwd triad -> swapped sides "
                      f"(posx={posx})")
    bone_map = build_bone_map(names, jpos, posx, negx)

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

    # side swap (profile "swap_sides"): mirror which MESH side drives each
    # canonical limb chain. The mesh's left/right assignment is invisible
    # on symmetric fighters, but asymmetric targets expose it — Samus's
    # cannon lives on her RIGHT arm, and a mirrored assignment puts the
    # replacement's LEFT hand there. Swapping canonical ids (not
    # posx/negx) keeps the facing triads untouched.
    if TARGET_SWAP_SIDES:
        _PSW = {8: 14, 14: 8, 9: 15, 15: 9, 10: 16, 16: 10,
                19: 24, 24: 19, 20: 25, 25: 20, 22: 27, 27: 22}
        _JSW = dict(_PSW)
        _JSW.update({21: 26, 26: 21})
        bone_map = {n: (_PSW.get(pp, pp), (None if jj is None else _JSW.get(jj, jj)))
                    for n, (pp, jj) in bone_map.items()}
        seg = {_PSW.get(k, k): v for k, v in seg.items()}
        print("side swap: mesh left/right chains mirrored onto canonical parts")

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
        # degenerate target bones (profile maps both endpoints onto one
        # joint — merged chains on crush-class targets) are not evidence
        # of scale; a median polluted by them collapses to ~0 and zeroes
        # the whole character (Kirby rendered as a handful of triangles).
        if Mlen > 1.0:
            ax_scales.append(Mlen/mlen)
    ax_sorted = sorted(ax_scales)
    s_perp = ax_sorted[len(ax_sorted)//2] if ax_sorted else 1.0
    # height-normalized global scale: the median bone ratio under-sizes
    # characters whose limb proportions differ from the target (a long-
    # legged mesh retargets to short bones -> small ratios). Match the
    # standing height instead: target (neck -> ankle) over mesh
    # (neck -> ankle), which is what a player perceives.
    try:
        # target top = highest head-part vertex of the vanilla fighter
        # (local -> world via the head joint's spawn frame), else neck
        _mtop = frames[11][0][1]
        _vp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), TARGET_PARTS_JSON or "vanilla-mario-parts.json")
        if os.path.exists(_vp_path):
            _vp = json.load(open(_vp_path))
            if "12" in _vp and 12 in frames:
                _o12, _R12 = frames[12]
                _mtop = max(_o12[1] + v[0]*_R12[0][1] + v[1]*_R12[1][1] + v[2]*_R12[2][1]
                            for v in _vp["12"])
        _ma = (frames[21][0][1] + frames[26][0][1]) / 2
        _tn = max(p[1] for p in pos)
        _ta = (jpos[name_idx[posx + "Foot"]][1] + jpos[name_idx[negx + "Foot"]][1]) / 2
        _sh = (_mtop - _ma) / max(1e-6, (_tn - _ta))
        if s_perp <= 1e-3 or 0.3 * s_perp < _sh < 3.0 * s_perp:
            print(f"global scale: height-normalized {s_perp:.1f} -> {_sh:.1f}")
            s_perp = _sh
    except (KeyError, IndexError):
        pass
    # profile tune "perp_boost": bulk multiplier for massive targets (DK).
    # Bone lengths pin the pose, so without it a human-thickness mesh
    # reads as a gangly skeleton inside the big fighter's stance.
    if "perp_boost" in TARGET_TUNE:
        s_perp *= float(TARGET_TUNE["perp_boost"])
        print(f"perp boost: x{TARGET_TUNE['perp_boost']} -> global scale {s_perp:.1f}")

    # ---- global facing alignment R_face. rot_between() alone is the
    # MINIMAL rotation between bone directions — twist about the bone
    # axis is unconstrained, so a torso that is vertical in both spaces
    # keeps the GLB's facing (+z, at the camera) regardless of which way
    # Mario actually faces (the identity test's vanilla twin exposed
    # this). Build the exact triad rotation taking the mesh (up,
    # shoulder-lateral) frame onto Mario's (torso-axis, shoulder-lateral)
    # spawn frame, and compose every per-bone Q on top of it.
    def triad(up, lat):
        u = normalize(list(up))
        l = [lat[k] - u[k]*sum(lat[j]*u[j] for j in range(3)) for k in range(3)]
        l = normalize(l)
        f = [u[1]*l[2]-u[2]*l[1], u[2]*l[0]-u[0]*l[2], u[0]*l[1]-u[1]*l[0]]
        return [u, l, f]  # rows

    m_up = [jpos[name_idx["neck"]][k] - jpos[name_idx["Hips"]][k] for k in range(3)]
    m_lat = [jpos[name_idx[posx+"Arm"]][k] - jpos[name_idx[negx+"Arm"]][k] for k in range(3)]
    g_up = [frames[11][0][k] - frames[6][0][k] for k in range(3)]
    g_lat = [frames[8][0][k] - frames[14][0][k] for k in range(3)]
    Tm, Tg = triad(m_up, m_lat), triad(g_up, g_lat)
    # R_face = Tg^T . Tm  (row-triads: mesh coords -> triad coords via Tm,
    # reconstruct in mario world via Tg^T)
    R_face = [[sum(Tg[a][r] * Tm[a][c] for a in range(3))
               for c in range(3)] for r in range(3)]

    # character forward directions (for twist control): fwd = lat x up,
    # orthonormalized inside triad(). rot_between() alone left the twist
    # about each bone axis arbitrary — thigh/upper-arm flesh could end up
    # rotated around the bone so knees/elbows read as bending sideways or
    # crossing. Build a FULL triad per bone (bone dir + twist reference)
    # in both spaces instead.
    def cross(a, b):
        return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]

    m_fwd = normalize(cross(m_lat, m_up))
    g_fwd = normalize(cross(g_lat, g_up))
    m_upn = normalize(list(m_up))
    g_upn = normalize(list(g_up))

    # parent part per part (the part whose distal joint is this part's
    # anchor) — used as the direction fallback for degenerate target bones
    _part_parent = {mario_bone[p]: p for p in seg if p not in INHERIT}
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
        # degenerate TARGET bone: profiles may map a part's proximal and
        # distal canonical joints onto the SAME target joint (Samus has no
        # left hand joint; crush-class targets merge whole chains). The
        # bone direction is then noise and the along-bone scale is zero —
        # the part renders as a flattened sheet. Continue along the parent
        # bone's direction at the global scale instead.
        if Mlen < 0.12 * s_perp * mlen:
            pp = _part_parent.get(part)
            if pp is not None and pp in frames and mario_bone.get(pp) in frames:
                PA, PB = frames[pp][0], frames[mario_bone[pp]][0]
                Pv = [PB[i]-PA[i] for i in range(3)]
                Plen = math.sqrt(sum(c*c for c in Pv))
                if Plen > 1e-6:
                    Mv = Pv
                    Mlen = Plen
            if Mlen < 1e-6:
                Mv = [0.0, -1.0, 0.0]
                Mlen = 1.0
            Mlen_eff = s_perp * mlen      # isotropic: no real bone to span
            print(f"degenerate target bone: part {part} follows its parent "
                  f"bone direction at global scale")
        else:
            Mlen_eff = Mlen
        # twist reference: forward, unless the bone runs near-parallel to
        # forward (then use up). Same choice on both sides keeps the
        # references corresponding.
        mvn = [c/mlen for c in mv]
        Mvn = [c/Mlen for c in Mv]
        # twist reference must be non-parallel to the bone in BOTH spaces:
        # the mesh arm is lateral (T-pose) but Mario's REAR forearm in the
        # spawn stance points almost along forward, so choosing by the
        # mesh bone alone built a degenerate game-side triad -> the rear
        # forearm rendered twisted/flattened on every character.
        _dm_f = abs(sum(mvn[k]*m_fwd[k] for k in range(3)))
        _dg_f = abs(sum(Mvn[k]*g_fwd[k] for k in range(3)))
        _dm_u = abs(sum(mvn[k]*m_upn[k] for k in range(3)))
        _dg_u = abs(sum(Mvn[k]*g_upn[k] for k in range(3)))
        if max(_dm_f, _dg_f) <= max(_dm_u, _dg_u):
            ref_m, ref_g = m_fwd, g_fwd
        else:
            ref_m, ref_g = m_upn, g_upn
        Tmb = triad(mvn, ref_m)
        Tgb = triad(Mvn, ref_g)
        Q = [[sum(Tgb[t][r] * Tmb[t][c] for t in range(3))
              for c in range(3)] for r in range(3)]
        u = [c/mlen for c in mv]
        # degenerate provider joints (e.g. a knee dropped at the ankle)
        # make Mlen/mlen explode and fling verts; clamp the bone-axis
        # scale to a sane band around the global scale.
        s_par = min(Mlen_eff / mlen, 3.0 * s_perp)
        # stretch compensation: long-limbed targets (Samus ~2x, DK/Yoshi
        # more) stretch parts along the bone while the perpendicular stays
        # at the global scale — thin spaghetti limbs that tear at seams.
        # The bone must still be spanned (the child part anchors at the
        # real joint), so widen the part instead: perp gains sqrt of the
        # stretch ratio, capped, keeping limbs readable at roughly the
        # authored aspect.
        # profile tune "widen_pow" (default 0.5 = sqrt): long-boned targets
        # need a stronger exponent — samus's cannon-side arm stretches
        # 2.7x but sqrt yields only 1.65x widening, leaving the sleeve at
        # 60% of its authored aspect ("unbelievably skinny arms").
        sp2 = s_perp * min(float(TARGET_TUNE.get("widen_cap", 1.55)),
                           max(1.0, s_par / s_perp)
                           ** float(TARGET_TUNE.get("widen_pow", 0.5)))
        conf[part] = (Q, s_par, sp2, u, a, A)

    # symmetrize left/right retarget scales: s_par divides by the MESH
    # side's bone length, and auto-rig joints aren't perfectly mirrored,
    # so the two sides picked up slightly different along-bone and perp
    # scales (lopsided limbs in motion). Average each pair.
    if "--no-symlimbs" not in sys.argv:
        for _pa, _pb in ((8, 14), (9, 15), (19, 24), (20, 25)):
            if _pa in conf and _pb in conf:
                _ca, _cb = conf[_pa], conf[_pb]
                _sp = (_ca[1] + _cb[1]) / 2.0
                _spp = (_ca[2] + _cb[2]) / 2.0
                conf[_pa] = (_ca[0], _sp, _spp, _ca[3], _ca[4], _ca[5])
                conf[_pb] = (_cb[0], _sp, _spp, _cb[3], _cb[4], _cb[5])

    if os.environ.get("OSB_DEBUG"):
        for part in sorted(conf):
            Q, sp, spp, u, a, A = conf[part]
            print(f"DBG conf part={part} s_par={sp:.3f} s_perp={spp:.3f} "
                  f"anchor_mesh=({a[0]:.2f},{a[1]:.2f},{a[2]:.2f}) "
                  f"anchor_mario=({A[0]:.1f},{A[1]:.1f},{A[2]:.1f})")

    # distal parts (head/hands/feet): parent's rotation, isotropic global
    # scale (no bone to span), own anchors
    # head scale (general): limbs/torso are locked to the target skeleton's
    # bone lengths, so standing height is fixed by the HEAD. Smash heads
    # are ~40% of height; a human-proportioned head at the global scale
    # leaves the fighter visibly short. Scale the head part so its top
    # lands at the vanilla head top (clamped to keep it sane).
    s_head = s_perp
    _mhead_h = 1.0
    try:
        _vp_path2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), TARGET_PARTS_JSON or "vanilla-mario-parts.json")
        if os.path.exists(_vp_path2) and 12 in frames and "Head" in name_idx:
            _vp2 = json.load(open(_vp_path2))
            _o12, _R12 = frames[12]
            _vtop = max(_o12[1] + v[0]*_R12[0][1] + v[1]*_R12[1][1] + v[2]*_R12[2][1]
                        for v in _vp2["12"])
            _vhead_h = _vtop - _o12[1]
            _mh = jpos[name_idx["Head"]][1]
            _mtop = max(p[1] for p in pos)
            _mhead_h = max(1e-6, _mtop - _mh)
            s_head = _vhead_h / _mhead_h
            s_head = max(s_perp, min(2.4 * s_perp, s_head))
            print(f"head scale: x{s_head:.1f} (global x{s_perp:.1f}) so head top "
                  f"matches vanilla ({_vhead_h:.0f} above head joint)")
    except (KeyError, IndexError, ValueError):
        pass
    for part in INHERIT:
        parent = INHERIT[part]
        Qp = conf[parent][0]
        a = jpos[name_idx[seg[part][0]]]
        A = frames[part][0]
        sp_ = s_head if part == 12 else s_perp
        if part == 12 and "head_recenter" in TARGET_TUNE and 6 in frames:
            # stooped skeletons (link, mildly luigi) park the HEAD JOINT
            # forward of the chest; mounting the oversized chibi head
            # there reads as a hunchback. Pull the anchor horizontally
            # back over the chest joint by this fraction (vertical kept).
            _f = float(TARGET_TUNE["head_recenter"])
            _C = frames[6][0]
            A = [A[0] + _f * (_C[0] - A[0]), A[1], A[2] + _f * (_C[2] - A[2])]
            print(f"head recenter: x{_f:.2f} toward the chest column")
        conf[part] = (Qp, sp_, sp_, [0.0, 1.0, 0.0], a, A)

    # feet get their OWN rotation: inheriting the calf's rotation leaves
    # the shoe pointing along the shin, i.e. toe-backward in the ankle
    # frame (vanilla foot geometry runs toe-forward along local +x). Align
    # mesh Foot->ToeBase onto the mario foot frame's +x axis instead.
    for part, foot_name in ((22, seg[22][0]), (27, seg[27][0])):
        toe_name = foot_name.replace("Foot", "ToeBase")
        if foot_name not in name_idx or toe_name not in name_idx:
            continue
        a = jpos[name_idx[foot_name]]
        b = jpos[name_idx[toe_name]]
        dir_m = [b[k] - a[k] for k in range(3)]
        mlen = math.sqrt(sum(c*c for c in dir_m)) or 1e-9
        ys_h = [p[1] for p in pos]
        if mlen < 0.02 * (max(ys_h) - min(ys_h)):
            # degenerate toe joint (dropped on the ankle) -> the aim
            # direction is noise; use the detected character forward.
            dir_mn = list(m_fwd)
            print(f"foot fix: degenerate toe segment on part {part}, using body forward")
        else:
            dir_mn = [c/mlen for c in dir_m]
        R = frames[part][1]
        dir_Mn = normalize([R[0][0], R[0][1], R[0][2]])   # local +x in world
        Tmb = triad(dir_mn, m_upn)
        Tgb = triad(dir_Mn, g_upn)
        Q = [[sum(Tgb[t][r] * Tmb[t][c] for t in range(3))
              for c in range(3)] for r in range(3)]
        A = frames[part][0]
        conf[part] = (Q, s_perp, s_perp, dir_mn, a, A)

    # profile tune "rigid_arms": long-boned targets (samus arm bones run
    # 2.7x the chibi mesh's) can't wear a stretched sleeve — graded
    # weights kink the long thin tube into a squiggle the moment the
    # elbow bends, and no widen exponent fixes articulation. Collapse
    # each arm to ONE rigid assembly at the authored proportions: every
    # arm part shares the SHOULDER part's conform (isotropic global
    # scale, anchored at the shoulder joint), and the weight collapse
    # further down rides the whole arm on that one joint. Stubby chibi
    # arms that swing cleanly — the same trade rigid_legs makes for
    # crush-class legs. The vanilla cannon (keep_vanilla) still renders
    # at the real hand joint, so reach stays readable.
    if TARGET_TUNE.get("rigid_arms"):
        # tune "arm_anchor": {"14": "distal"} anchors that chain at its
        # HAND end instead of the shoulder — for samus's cannon arm the
        # fist must LIVE inside the kept vanilla cannon (joint 16), and
        # the cannon moves with the elbow, which a shoulder-anchored stub
        # can't follow (the floating-box-at-the-hip run frames). The
        # whole assembly rides the distal joint; the shoulder end blends
        # into the torso band instead.
        _anch = TARGET_TUNE.get("arm_anchor", {})
        for root, kids in ((8, (9, 10)), (14, (15, 16))):
            if root not in conf:
                continue
            Q, _sa, _sp2, u, a, A = conf[root]
            conf[root] = (Q, s_perp, s_perp, u, a, A)
            if _anch.get(str(root)) == "distal":
                # TWO rigid segments, vanilla-N64 style: the upper stub
                # stays on the shoulder; forearm+hand form a second rigid
                # piece anchored fist-in-cannon at the distal joint. A
                # whole-arm assembly on the cannon turned the sleeve into
                # a torn banner whenever the run pose held the cannon
                # vertical; segmenting swaps that for the classic small
                # elbow gap, which the overlap copies mask.
                hand_part = kids[-1]
                _hname = next((n for n, (pp, _) in bone_map.items()
                               if pp == hand_part and "Hand" in n), None)
                if _hname is not None and hand_part in frames:
                    lower = (Q, s_perp, s_perp, u,
                             jpos[name_idx[_hname]], frames[hand_part][0])
                    for k in kids:
                        conf[k] = lower
                else:
                    for k in kids:
                        conf[k] = conf[root]
            else:
                for k in kids:
                    conf[k] = conf[root]
        print("rigid arms: arm chains rigid at authored proportions"
              + (f" (distal-anchored: {sorted(_anch)})" if _anch else ""))

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

    # ---- side correction (general): on fused/touching limbs (shoes
    # meshed as one blob) providers interleave left/right weights within
    # the blob; the stance separation then tears it apart. Trust the
    # GEOMETRY: a vert on the left of the body midline gets left-side
    # parts (mirror-mapping any right weights), and vice versa. Lateral
    # axis is z (character faces +/-x, handled by the facing fix).
    _MIRs = {8: 14, 9: 15, 10: 16, 19: 24, 20: 25, 22: 27}
    _MIRs.update({v: k for k, v in _MIRs.items()})
    _lo_parts = {19, 20, 22, 24, 25, 27}
    # lateral axis from the hip joints themselves (works for any facing)
    n_side = 0
    if (posx + "UpLeg") in name_idx and (negx + "UpLeg") in name_idx:
        _pL = jpos[name_idx[posx + "UpLeg"]]
        _pR = jpos[name_idx[negx + "UpLeg"]]
        _lat_v = [_pL[k] - _pR[k] for k in range(3)]
        _mid_pt = [(_pL[k] + _pR[k]) / 2 for k in range(3)]
        def _sidec(_pp):
            return sum((_pp[k] - _mid_pt[k]) * _lat_v[k] for k in range(3))
        for _i, _p in enumerate(pos):
            vw = vweights[_i]
            if not any(q in _lo_parts for q in vw):
                continue
            want_left = _sidec(_p) > 0
            vw2 = {}
            for q, w in vw.items():
                if q in _lo_parts:
                    is_left = q in {19, 20, 22}
                    if is_left != want_left:
                        q = _MIRs[q]
                        n_side += 1
                vw2[q] = vw2.get(q, 0.0) + w
            vweights[_i] = vw2
            vpart[_i] = max(vw2, key=vw2.get)
    if n_side:
        print(f"side fix: {n_side} leg/foot weights mirrored to match geometry")
    # ...and the PROVIDER bone indices too: the LBS world authoring maps
    # verts through per-meshy-bone anchors, so a right-side vert carrying
    # LeftFoot bones still tears away from its neighbors even after the
    # part weights are corrected.
    _LEGW = ("UpLeg", "Leg", "Foot", "ToeBase")
    _bmirror = {}
    for _n, _idx in name_idx.items():
        if any(_n == "Left" + s or _n == "Right" + s for s in _LEGW):
            _other = ("Right" + _n[4:]) if _n.startswith("Left") else ("Left" + _n[5:])
            if _other in name_idx:
                _bmirror[_idx] = name_idx[_other]
    n_bside = 0
    if "LeftUpLeg" in name_idx and "RightUpLeg" in name_idx and _bmirror:
        _bL = jpos[name_idx["LeftUpLeg"]]
        _bR = jpos[name_idx["RightUpLeg"]]
        _blat = [_bL[k] - _bR[k] for k in range(3)]
        _bmid = [(_bL[k] + _bR[k]) / 2 for k in range(3)]
        for _i, _p in enumerate(pos):
            want_left = sum((_p[k] - _bmid[k]) * _blat[k] for k in range(3)) > 0
            ji = list(jix[_i])
            changed = False
            for _k in range(4):
                bn = names[ji[_k]]
                if not any(s in bn for s in _LEGW):
                    continue
                is_left = bn.startswith("Left")
                if is_left != want_left and ji[_k] in _bmirror:
                    ji[_k] = _bmirror[ji[_k]]
                    changed = True
            if changed:
                jix[_i] = type(jix[_i])(ji) if not isinstance(jix[_i], list) else ji
                n_bside += 1
    if n_bside:
        print(f"side fix (bones): {n_bside} verts' provider leg bones mirrored")

    # ---- part-weight smoothing (general): provider weights are often
    # hard per-bone, so garments that overhang a joint (jacket hems over
    # thighs) get triangles whose verts map to parts with very different
    # retarget transforms -> shard tears. Diffuse the PART weights over
    # the position-welded mesh graph so boundaries blend over a band;
    # the CPU-skinned path renders soft blends correctly.
    _wk = {}
    for _i, _p in enumerate(pos):
        _wk.setdefault((round(_p[0], 3), round(_p[1], 3), round(_p[2], 3)), []).append(_i)
    _rep = {}
    for _g in _wk.values():
        for _i in _g:
            _rep[_i] = _g[0]
    _adj = {}
    for _a, _b, _c in tris:
        _ra, _rb, _rc = _rep[_a], _rep[_b], _rep[_c]
        for _x, _y in ((_ra, _rb), (_ra, _rc), (_rb, _rc)):
            if _x != _y:
                _adj.setdefault(_x, set()).add(_y)
                _adj.setdefault(_y, set()).add(_x)
    _cur = {r: dict(vweights[r]) for r in _adj}
    for _it in range(8):
        _nxt = {}
        for r, nbrs in _adj.items():
            acc2 = {p: 0.5 * w for p, w in _cur[r].items()}
            share = 0.5 / len(nbrs)
            for nb in nbrs:
                for p, w in _cur[nb].items():
                    acc2[p] = acc2.get(p, 0.0) + share * w
            top = sorted(acc2.items(), key=lambda kv: -kv[1])[:4]
            tot = sum(w for _, w in top) or 1.0
            _nxt[r] = {p: w / tot for p, w in top if w / tot > 0.04}
        _cur = _nxt
    for _i in range(len(pos)):
        r = _rep[_i]
        if r in _cur and _cur[r]:
            vweights[_i] = dict(_cur[r])
            vpart[_i] = max(vweights[_i], key=vweights[_i].get)
    # never blend across the body midline: a vert carrying weight on a
    # part AND its mirror (touching shoes/thighs weld the graphs) gets
    # averaged into the middle -> cross-leg sliver shards. Keep only the
    # heavier side.
    _MIR = {8: 14, 9: 15, 10: 16, 19: 24, 20: 25, 22: 27}
    _MIR.update({v: k for k, v in _MIR.items()})
    _LEFTS = {8, 9, 10, 19, 20, 22}
    n_purged = 0
    for _i in range(len(pos)):
        vw = vweights[_i]
        if not any(p in vw and _MIR.get(p) in vw for p in vw):
            continue
        lsum = sum(w for p, w in vw.items() if p in _LEFTS)
        rsum = sum(w for p, w in vw.items() if _MIR.get(p) in _LEFTS)
        drop = (_LEFTS if lsum < rsum else {_MIR[p] for p in _LEFTS})
        vw2 = {p: w for p, w in vw.items() if p not in drop}
        tot = sum(vw2.values()) or 1.0
        vweights[_i] = {p: w / tot for p, w in vw2.items()}
        vpart[_i] = max(vweights[_i], key=vweights[_i].get)
        n_purged += 1
    if n_purged:
        print(f"midline purge: {n_purged} cross-side verts cleaned")
    # drop bridge triangles that span mirror parts (fused touching limbs
    # in the provider mesh — e.g. shoes meshed as one blob): they tear
    # into slivers when the stance separates the limbs. The hole faces
    # the opposite limb and is effectively invisible in play.
    # (cross-limb bridge triangles are handled by the stretch-ratio cut
    # at emit time; a part-id-only cut removed legitimate crotch/inseam
    # triangles and left holes)

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

    _bsw = (lambda j: {8: 14, 14: 8, 9: 15, 15: 9, 10: 16, 16: 10, 7: 13, 13: 7,
                        19: 24, 24: 19, 20: 25, 25: 20, 21: 26, 26: 21}.get(j, j)) \
           if TARGET_SWAP_SIDES else (lambda j: j)
    bone_target = {
        "Hips": mario_o(6),
        "neck": mario_o(11), "Head": mario_o(12),
        posx + "Shoulder": mario_o(_bsw(7)), negx + "Shoulder": mario_o(_bsw(13)),
        posx + "Arm": mario_o(_bsw(8)), posx + "ForeArm": mario_o(_bsw(9)), posx + "Hand": mario_o(_bsw(10)),
        negx + "Arm": mario_o(_bsw(14)), negx + "ForeArm": mario_o(_bsw(15)), negx + "Hand": mario_o(_bsw(16)),
        posx + "UpLeg": mario_o(_bsw(19)), posx + "Leg": mario_o(_bsw(20)), posx + "Foot": mario_o(_bsw(21)),
        negx + "UpLeg": mario_o(_bsw(24)), negx + "Leg": mario_o(_bsw(25)), negx + "Foot": mario_o(_bsw(26)),
    }

    # torso anisotropic map (general, shear-free): the torso has FIVE
    # attachment points (hip joints x2, arm roots x2, neck). A full affine
    # fit introduces shear that stretches the torso internally; instead
    # use rotation (triad) + three orthogonal scales: vertical from the
    # hips->neck length ratio, LATERAL from the hip-width & shoulder-width
    # ratios, depth from the global scale. Residual limb-root gaps are
    # small and blend out through the weights.
    _torso_bones = {"Hips", "Spine", "Spine01", "Spine02",
                    posx + "Shoulder", negx + "Shoulder"}
    torso_aniso = None
    try:
        _mhw = math.dist(jpos[name_idx[posx + "UpLeg"]], jpos[name_idx[negx + "UpLeg"]])
        _Mhw = math.dist(frames[19][0], frames[24][0])
        _msw = math.dist(jpos[name_idx[posx + "Arm"]], jpos[name_idx[negx + "Arm"]])
        _Msw = math.dist(frames[8][0], frames[14][0])
        _s_lat = math.sqrt((_Mhw / max(_mhw, 1e-6)) * (_Msw / max(_msw, 1e-6)))
        _Q6, _s6ax, _s6p, _u6, _a6, _A6 = conf[6]
        _latn = normalize(list(m_lat))
        # orthogonalize lateral against the bone (up) axis
        _dot = sum(_latn[k] * _u6[k] for k in range(3))
        _latn = normalize([_latn[k] - _dot * _u6[k] for k in range(3)])
        _depn = normalize(cross(_u6, _latn))
        torso_aniso = (_Q6, _s6ax, _s_lat, _s6p, _u6, _latn, _depn, _a6, _A6)
        print(f"torso map: vertical x{_s6ax:.1f}, lateral x{_s_lat:.1f} "
              f"(hip ratio {_Mhw/max(_mhw,1e-6):.1f}, shoulder ratio {_Msw/max(_msw,1e-6):.1f}), depth x{_s6p:.1f}")
    except (KeyError, IndexError):
        pass

    def bone_apply(bname, v):
        part = bone_map.get(bname, (6, 11))[0]
        if torso_aniso is not None and bname in _torso_bones:
            Qt, sv, sl, sd, ut, lt, dp, at, At = torso_aniso
            d = [v[k] - at[k] for k in range(3)]
            cv = sum(d[k] * ut[k] for k in range(3))
            cl = sum(d[k] * lt[k] for k in range(3))
            cd = sum(d[k] * dp[k] for k in range(3))
            d = [ut[k] * cv * sv + lt[k] * cl * sl + dp[k] * cd * sd for k in range(3)]
            d = mat_apply(Qt, d)
            return [d[k] + At[k] for k in range(3)]
        Q, s_ax, sp, u, a, A = conf[part]
        tgt = bone_target.get(bname)
        if tgt is not None:
            a = jpos[name_idx[bname]]
            A = tgt
        d = [v[k]-a[k] for k in range(3)]
        if part == 12 and s_head != s_perp:
            # head scale ramps in with height above the head joint: body
            # scale at the neck/chin, full head scale from the face line
            # up. An isotropic scale about the joint stretched the neck
            # band into a cone (very visible at the taunt camera zoom).
            hj = jpos[name_idx["Head"]]
            hy = sum((v[k] - hj[k]) * m_upn[k] for k in range(3))
            t = min(1.0, max(0.0, hy / max(1e-6, 0.25 * _mhead_h)))
            t = t * t * (3 - 2 * t)
            s_loc = s_perp + (s_head - s_perp) * t
            d = [c * s_loc for c in d]
            d = mat_apply(Q, d)
            return [d[k] + A[k] for k in range(3)]
        ax = d[0]*u[0] + d[1]*u[1] + d[2]*u[2]
        d = [u[k]*ax*s_ax + (d[k] - u[k]*ax)*sp for k in range(3)]
        d = mat_apply(Q, d)
        return [d[k] + A[k] for k in range(3)]

    # ---- uniform conform (profile "conform": "uniform"): crush-class
    # targets (Kirby/Pikachu/Purin) map the humanoid chain onto 1-2
    # segment stubs, and the per-bone conform crushes the mesh into a
    # blob. Keep the character INTACT instead: ONE rigid similarity
    # transform for every vertex (facing rotation + uniform scale to the
    # target's standing height, feet on the target's ground plane) while
    # the part weights still bind to the mapped target joints, so the
    # mini figure rides and articulates with the fighter's animations.
    if TARGET_CONFORM == "uniform":
        # world up, NOT the target spine: hunched targets (Yoshi's
        # forward-pitched spine, Pikachu's crouch) would tilt the whole
        # figure diagonally, and the point of uniform mode is an intact
        # upright character. (Merged chains also leave the spine
        # degenerate on Kirby/Purin anyway.)
        _g_up_u = [0.0, 1.0, 0.0]
        _g_lat_u = list(g_lat)
        if math.sqrt(sum(c * c for c in _g_lat_u)) < 1e-3:
            _g_lat_u = [0.0, 0.0, 1.0]
        Tg_u = triad(_g_up_u, _g_lat_u)
        R_u = [[sum(Tg_u[t][r] * Tm[t][c] for t in range(3)) for c in range(3)]
               for r in range(3)]
        _pj_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                TARGET_PARTS_JSON or "vanilla-mario-parts.json")
        _pj = json.load(open(_pj_path))
        _tys = [frames[int(pid)][0][1] + v[0] * frames[int(pid)][1][0][1]
                + v[1] * frames[int(pid)][1][1][1] + v[2] * frames[int(pid)][1][2][1]
                for pid, verts in _pj.items() if int(pid) in frames for v in verts]
        if _tys:
            _t_top, _t_bot = max(_tys), min(_tys)
        else:
            # no canonical-part geometry dumped (Yoshi: body lives on
            # unmapped chain joints) — span the target's FULL joint set
            # from the skel dump, with a head margin above the top joint.
            import re as _re
            _jys = [float(m.group(1)) for L in open(frames_path)
                    for m in [_re.match(
                        r"SKELDUMP: joint=\d+ parent=\S+ "
                        r"world=\([-\d.]+,([-\d.]+),[-\d.]+\)", L)] if m]
            _t_bot, _t_top = min(_jys), max(_jys)
            _t_top += 0.18 * (_t_top - _t_bot)
        # optional chibi warp (tune "head_boost"/"leg_squash"): ball-shaped
        # targets read best as giant-head + stubby-leg figures, not a
        # proportional mini human. Boost scales the head uniformly about
        # the neck (smoothstep band so the collar doesn't crease); squash
        # compresses below-hip verts vertically toward the hips. Runs in
        # MESH space before the similarity, so the height normalization
        # below fits the warped figure into the target height.
        _hb = float(TARGET_TUNE.get("head_boost", 1.0))
        _lsq = float(TARGET_TUNE.get("leg_squash", 1.0))
        if _hb != 1.0 or _lsq != 1.0:
            _ny_c = jpos[name_idx["neck"]][1]
            _hy_c = jpos[name_idx["Hips"]][1]
            _npt_c = jpos[name_idx["neck"]]
            _H0_c = (max(p[1] for p in pos) - min(p[1] for p in pos)) or 1e-9
            _bw_c = 0.10 * _H0_c

            def _chibi(v):
                x, y, z = v
                if _lsq != 1.0 and y < _hy_c:
                    y = _hy_c + (y - _hy_c) * _lsq
                if _hb != 1.0:
                    t = max(0.0, min(1.0, (v[1] - (_ny_c - _bw_c)) / (2 * _bw_c)))
                    t = t * t * (3 - 2 * t)
                    sc = 1.0 + (_hb - 1.0) * t
                    x = _npt_c[0] + (x - _npt_c[0]) * sc
                    y = _npt_c[1] + (y - _npt_c[1]) * sc
                    z = _npt_c[2] + (z - _npt_c[2]) * sc
                return [x, y, z]
            print(f"chibi warp: head x{_hb}, legs x{_lsq}")
        else:
            def _chibi(v):
                return list(v)
        _wpos = [_chibi(p) for p in pos]
        _mys = [p[1] for p in _wpos]
        s_u = ((_t_top - _t_bot) / max(1e-6, max(_mys) - min(_mys))
               * float(TARGET_TUNE.get("uniform_height", 1.0)))
        _aL = _chibi(jpos[name_idx[posx + "Foot"]])
        _aR = _chibi(jpos[name_idx[negx + "Foot"]])
        _anc = [(_aL[k] + _aR[k]) / 2 for k in range(3)]
        _rootP = frames[0][0] if 0 in frames else frames[6][0]
        _P = [_rootP[0], _t_bot + s_u * (_anc[1] - min(_mys)), _rootP[2]]

        def bone_apply(bname, v, _R=R_u, _s=s_u, _a=_anc, _p=_P, _w=_chibi):
            vw = _w(v)
            d = mat_apply(_R, [(vw[k] - _a[k]) * _s for k in range(3)])
            return [d[k] + _p[k] for k in range(3)]
        print(f"uniform conform: scale x{s_u:.2f} to target height "
              f"{_t_top - _t_bot:.0f} ({_t_bot:.0f}..{_t_top:.0f}), "
              f"feet on ground at root x/z")

    # ---- authored world position = linear-blend skinning over the
    # per-bone maps with the real skin weights. At spawn the mesh is an
    # exact smooth skinned pose: gapless, no baked stretch, and every
    # duplicated copy of a boundary triangle is IDENTICAL at rest (tears
    # only open as joints deviate from spawn, and the overlap copies mask
    # them from both sides — the vanilla N64 approach).
    def lbs(apply_fn):
        out = []
        for i, v in enumerate(pos):
            ji, wt = jix[i], wts[i]
            tot = sum(max(w, 0.0) for w in wt) or 1.0
            acc = [0.0, 0.0, 0.0]
            for k in range(4):
                if wt[k] <= 0.0:
                    continue
                bw = apply_fn(names[ji[k]], v)
                for c in range(3):
                    acc[c] += bw[c] * wt[k] / tot
            out.append(acc)
        return out

    world = lbs(bone_apply)
    if os.environ.get("OSB_DEBUG"):
        # pivot agreement check: child joint through parent map vs own map
        for _side in ("Left", "Right"):
            for _pa, _ch in ((_side+"UpLeg", _side+"Leg"), (_side+"Leg", _side+"Foot"),
                             ("Hips", _side+"UpLeg"), ("Spine02", _side+"Shoulder"),
                             (_side+"Shoulder", _side+"Arm"), (_side+"Arm", _side+"ForeArm"),
                             (_side+"ForeArm", _side+"Hand"), ("neck", "Head")):
                if _pa in name_idx and _ch in name_idx:
                    jv = jpos[name_idx[_ch]]
                    p1 = bone_apply(_pa, jv); p2 = bone_apply(_ch, jv)
                    gap = math.dist(p1, p2)
                    print(f"DBG pivot {_pa:>13s}->{_ch:<13s} gap={gap:7.1f}  "
                          f"parent_map_part={bone_map.get(_pa,(6,))[0]} child_part={bone_map.get(_ch,(6,))[0]}")

    # ---- part-profile conform: per mario part, affine-map the authored
    # local vertex distribution (in the joint's rest frame) onto the
    # VANILLA part's bounds (vanilla-mario-parts.json, dumped from the
    # game's own model DLs). This is what makes the character read as a
    # Smash 64 fighter: giant head, big gloves, stubby slim legs. The
    # bone axis of limb parts is left untouched so bone endpoints keep
    # landing exactly on the mario joints. Composed per-BONE below, so
    # LBS still blends smoothly across part seams.
    import os as _os
    _vanilla_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                  "vanilla-mario-parts.json")
    # --no-profile: skip the Mario-part-bounds fit (per-part thickness
    # scales disagree at part boundaries and tear non-chibi meshes);
    # keep only the bone retarget + uniform global scale.
    # profile tune "target_part_fit": fit part spans to the TARGET
    # fighter's own dumped bounds instead of Mario's — on crush-class
    # targets a Mario-sized boot wraps a Pikachu-sized leg otherwise.
    _tpf = bool(TARGET_TUNE.get("target_part_fit")) and TARGET_PARTS_JSON
    if _tpf:
        _vanilla_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                      TARGET_PARTS_JSON)
    vanilla_parts = ({} if ("--no-profile" in sys.argv or TARGET_CONFORM == "uniform"
                            or TARGET_TUNE.get("no_part_fit")) else
                     (json.load(open(_vanilla_path)) if _os.path.exists(_vanilla_path) else {}))

    # dominant part per vertex (needed for the fit; recomputed identically
    # for triangle assignment later)
    vpart_fit = []
    for ji, wt in zip(jix, wts):
        acc = {}
        for k in range(4):
            if wt[k] <= 0.0:
                continue
            part = bone_map.get(names[ji[k]], (6, 11))[0]
            acc[part] = acc.get(part, 0.0) + wt[k]
        vpart_fit.append(max(acc, key=acc.get) if acc else 6)

    FREE_PARTS = {12, 10, 16, 22, 27}      # head/hands/feet: fit all axes
    SCALE_MIN, SCALE_MAX = 0.6, 2.4

    def pctl(vals, q):
        s = sorted(vals)
        return s[max(0, min(len(s) - 1, int(q * len(s))))]

    part_T = {}   # part -> (scale3, offset3) in the part joint's rest frame
    for part in set(vpart_fit):
        if TARGET_TUNE.get("rigid_arms") and part in (8, 9, 10, 14, 15, 16):
            # rigid arm assemblies keep their authored shape/position —
            # per-part bounds fitting would re-center the hands into the
            # vanilla glove boxes and rip the assembly into fragments
            # (captain's extended bind put those boxes far from the stub)
            continue
        van = vanilla_parts.get(str(part))
        pts = [world[i] for i in range(len(world)) if vpart_fit[i] == part]
        if not van or len(pts) < 8 or part not in frames:
            continue
        o, R = frames[part]
        Rinv = inv3(R)
        loc = [row_apply([p[k] - o[k] for k in range(3)], Rinv) for p in pts]

        # axial local axis (kept fixed) for parts that span a mario bone
        ax_axis = -1
        if part in mario_bone and part not in FREE_PARTS:
            B = frames[mario_bone[part]][0]
            d = row_apply([B[k] - o[k] for k in range(3)], Rinv)
            ax_axis = max(range(3), key=lambda k: abs(d[k]))

        scale = [1.0, 1.0, 1.0]
        off = [0.0, 0.0, 0.0]
        for axis in range(3):
            if axis == ax_axis:
                continue
            # our spans use tight percentiles whose tails then overshoot the
            # vanilla bounds — the fighter read a size class bigger than the
            # in-frame vanilla twin. Wider percentiles + a small global
            # shrink keeps the silhouette at vanilla size.
            SPAN_TRIM = 1.0 if part == 12 else 1.02  # verifier: body reads slimmer than vanilla
            vc = (min(v[axis] for v in van) + max(v[axis] for v in van)) / 2.0
            vh = (max(v[axis] for v in van) - min(v[axis] for v in van)) / 2.0 * SPAN_TRIM
            vmin, vmax = vc - vh, vc + vh
            pmin = pctl([l[axis] for l in loc], 0.005)
            pmax = pctl([l[axis] for l in loc], 0.995)
            pspan = pmax - pmin
            vspan = vmax - vmin
            if pspan < 1e-3 or vspan < 1e-3:
                continue
            if _tpf:
                # target-bounds fit: the per-part floors below are Mario
                # aesthetics ("boots are chunky") — on a crush target they
                # forbid exactly the shrink we need. Allow deep shrink.
                s = max(0.35, min(SCALE_MAX, vspan / pspan))
                scale[axis] = s
                if part in FREE_PARTS:
                    off[axis] = (vmin + vmax) / 2.0 - (pmin + pmax) / 2.0 * s
                continue
            s = max(SCALE_MIN, min(SCALE_MAX, vspan / pspan))
            if part in (22, 27):
                s = max(1.0, min(1.5, s))  # vanilla boots are chunky
            if part in (8, 14):
                # upper-arm sleeves ballooning past 1.3 clip through the
                # gloves in bent-arm poses
                s = min(1.3, s)
            if part in (10, 16):
                s = max(1.0, min(1.45, s))  # vanilla gloves are BIG
            if part in (20, 25):
                # calves: fattening the pant cuff makes it poke out below
                # the shoes when the knee/ankle bend in crouches.
                s = max(0.85, min(1.12, s))
            if part in (19, 24, 20, 25):
                # never THIN the legs below vanilla — slim legs read lanky
                s = max(1.12, s)
            scale[axis] = s
            # Perp-plane offsets shift limb flesh off the bone line, which
            # reads as scissor-legs / drifting arms in motion. Only the
            # anchored extremity parts (head/hands/feet) get recentered;
            # limb + torso parts keep their bone-centered distribution.
            if part in FREE_PARTS:
                off[axis] = (vmin + vmax) / 2.0 - (pmin + pmax) / 2.0 * s
        part_T[part] = (scale, off)

    # symmetrize left/right pairs: auto-rig asymmetries (one shoe's verts
    # spilling into the calf, etc.) otherwise give each side a different
    # scale and the fighter reads lopsided in motion.
    MIRROR_PAIRS = [(8, 14), (9, 15), (10, 16), (19, 24), (20, 25), (22, 27)]
    for pa, pb in MIRROR_PAIRS:
        Ta, Tb = part_T.get(pa), part_T.get(pb)
        if Ta is None or Tb is None:
            continue
        for axis in range(3):
            # scales are magnitudes -> average; offsets stay per-side (they
            # target the already-mirrored vanilla bounds in local frames).
            s = (Ta[0][axis] + Tb[0][axis]) / 2.0
            Ta[0][axis] = Tb[0][axis] = s

    def part_conform(part, w):
        T = part_T.get(part)
        if T is None:
            return w
        scale, off = T
        o, R = frames[part]
        l = row_apply([w[k] - o[k] for k in range(3)], inv3(R))
        l = [l[k] * scale[k] + off[k] for k in range(3)]
        d = mat_apply([[R[0][0], R[1][0], R[2][0]],
                       [R[0][1], R[1][1], R[2][1]],
                       [R[0][2], R[1][2], R[2][2]]], l)
        return [d[k] + o[k] for k in range(3)]

    def bone_apply_conformed(bname, v):
        part = bone_map.get(bname, (6, 11))[0]
        return part_conform(part, bone_apply(bname, v))

    if "head_recenter" in TARGET_TUNE and 12 in part_T and 12 in frames and 6 in frames:
        # the bounds fit centers our head into the VANILLA head part's box,
        # which on stooped skeletons (link) sits forward of the chest —
        # the hunchback mount. Compute where that box center lands in the
        # world and pull the head back over the chest column.
        _f = float(TARGET_TUNE["head_recenter"])
        _o12, _R12 = frames[12]
        _C = frames[6][0]
        _van12 = vanilla_parts.get("12")
        _vc = [(min(v[a] for v in _van12) + max(v[a] for v in _van12)) / 2.0
               for a in range(3)]
        _cw = [row_apply(_vc, _R12)[k] + _o12[k] for k in range(3)]
        _dw = [_f * (_C[0] - _cw[0]), 0.0, _f * (_C[2] - _cw[2])]
        _dl = row_apply(_dw, inv3(_R12))
        _sc12, _off12 = part_T[12]
        part_T[12] = (_sc12, [_off12[k] + _dl[k] for k in range(3)])
        print(f"head recenter: x{_f:.2f} toward the chest column "
              f"(world d=({_dw[0]:.0f},{_dw[2]:.0f}))")
    if part_T:
        world = lbs(bone_apply_conformed)
        print("part-profile conform:",
              {p: [round(s, 2) for s in T[0]] for p, T in sorted(part_T.items())})


    # ---- displacement-field smoothing (general): per-bone retarget maps
    # can't all agree where proportions differ from the target skeleton,
    # leaving seam tears (high-frequency jumps in world - rigid(bind)).
    # Diffuse the displacement field over the position-welded mesh graph:
    # tears close, low-frequency retarget shape and joint placement stay.
    if "--smooth-disp" in sys.argv:  # off by default: it diffuses intended pose rotations away
        import numpy as _nds
        _B = _nds.array(pos, _nds.float64); _W = _nds.array(world, _nds.float64)
        # global similarity bind->world (Kabsch + uniform scale)
        _bc = _B.mean(0); _wc = _W.mean(0)
        _Bc = _B - _bc; _Wc = _W - _wc
        _U, _S, _Vt = _nds.linalg.svd(_Bc.T @ _Wc)
        _d = _nds.sign(_nds.linalg.det(_Vt.T @ _U.T))
        _R = _Vt.T @ _nds.diag([1, 1, _d]) @ _U.T
        _sc = _S.sum() / (_Bc ** 2).sum() if (_Bc ** 2).sum() > 0 else 1.0
        _G = (_sc * (_R @ _Bc.T)).T + _wc
        _D = _W - _G
        # adjacency (position-welded)
        _key = {}
        for _i, _p in enumerate(pos):
            _key.setdefault((round(_p[0], 3), round(_p[1], 3), round(_p[2], 3)), []).append(_i)
        _rep = _nds.arange(len(pos))
        for _g in _key.values():
            for _i in _g: _rep[_i] = _g[0]
        _nb = {}
        for _a, _b2, _c in tris:
            _ra, _rb, _rc = _rep[_a], _rep[_b2], _rep[_c]
            for _x, _y in ((_ra, _rb), (_ra, _rc), (_rb, _rc)):
                if _x != _y:
                    _nb.setdefault(_x, set()).add(_y); _nb.setdefault(_y, set()).add(_x)
        _reps = _nds.array(sorted(_nb))
        _nbl = [_nds.fromiter(_nb[r], int) for r in _reps]
        _Dr = _D[_reps].copy()
        _ridx = {int(r): k for k, r in enumerate(_reps)}
        _nbk = [_nds.array([_ridx[int(n)] for n in l]) for l in _nbl]
        # TARGETED: only vertices in tear zones move. Seed = verts on an
        # edge stretched > 2x; dilate 6 rings; everything else is a fixed
        # boundary condition so intentional detail (face) isn't smeared.
        _Gr = _G[_reps]; _Br = _B[_reps]
        _free = _nds.zeros(len(_reps), bool)
        for k in range(len(_reps)):
            db = _nds.linalg.norm(_Br[_nbk[k]] - _Br[k], axis=1) * _sc + 1e-6
            dw = _nds.linalg.norm((_Gr[_nbk[k]] + _Dr[_nbk[k]]) - (_Gr[k] + _Dr[k]), axis=1)
            if (dw > 2.0 * db).any():
                _free[k] = True
        for _ring in range(6):
            _grow = _free.copy()
            for k in _nds.where(_free)[0]:
                _grow[_nbk[k]] = True
            _free = _grow
        n_free = int(_free.sum())
        _fidx = _nds.where(_free)[0]
        for _it in range(60):
            _new = _Dr.copy()
            for k in _fidx:
                _new[k] = 0.5 * _Dr[k] + 0.5 * _Dr[_nbk[k]].mean(0)
            _Dr = _new
        print(f"disp smoothing: targeted, {n_free}/{len(_reps)} verts in tear zones")
        _Dfull = _D.copy()
        for _i in range(len(pos)):
            _r = int(_rep[_i])
            if _r in _ridx:
                _Dfull[_i] = _Dr[_ridx[_r]]
        _Wn = _G + _Dfull
        _moved = _nds.linalg.norm(_Wn - _W, axis=1)
        world = [tuple(map(float, w)) for w in _Wn]
        print(f"  max vert move {_moved.max():.1f}, mean {_moved.mean():.1f}")

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
    OVERLAP_W = 0.25
    # VANILLA-STYLE OVERLAP (rigid-consistent). Each part takes its
    # majority triangles PLUS an extension band past every cut (any tri
    # where every vertex holds >= EXT_W weight in the part). Crucially,
    # a part's copy of a vertex is authored through the part's OWN bones
    # only (restricted LBS, below) — extensions move rigidly WITH their
    # part and interpenetrate the neighbor under rotation, exactly like
    # the vanilla models' overlapping joint volumes. This is what kills
    # the hole/discontinuity feel: joints never open a visible gap
    # because both sides own flesh that reaches through the joint.
    EXT_W = 0.10
    parts = {}
    overlap = {}     # legacy structure, kept empty
    for t in tris:
        owners = {vpart[i] for i in t}
        avgw = {j: sum(vweights[i].get(j, 0.0) for i in t) / 3.0 for j in owners}
        main = max(avgw, key=avgw.get)
        parts.setdefault(main, []).append(t)
        cand = set(vweights[t[0]].keys())
        for i in t[1:]:
            cand &= set(vweights[i].keys())
        for j in cand:
            if j == main:
                continue
            if all(vweights[i].get(j, 0.0) >= EXT_W for i in t):
                parts.setdefault(j, []).append(t)

    # restricted-LBS authoring: position of vertex i as seen by `part`,
    # using only the bones that belong to that part (renormalized).
    def part_world(part, i):
        ji, wt = jix[i], wts[i]
        acc = [0.0, 0.0, 0.0]
        tot = 0.0
        for k in range(4):
            if wt[k] <= 0.0:
                continue
            bname = names[ji[k]]
            if bone_map.get(bname, (6, 11))[0] != part:
                continue
            bw = part_conform(part, bone_apply(bname, pos[i]))
            for c in range(3):
                acc[c] += bw[c] * wt[k]
            tot += wt[k]
        if tot <= 0.0:
            return world[i]
        return [c / tot for c in acc]

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
        # Meshy albedo already carries baked AO/shading; a deep baked
        # diffuse on top reads much darker than the vanilla lit fighters.
        # Keep only a shallow shading ramp.
        return min(1.0, 0.72 + 0.28*max(0.0, d))

    # ---- authored-mesh normals. Rotating source normals by each vert's
    # DOMINANT part Q shades seam-adjacent verts discontinuously — the
    # dark triangular crease streaks at the crotch/thighs every verifier
    # flagged. Recompute smooth area-weighted normals on the AUTHORED
    # world mesh (welded by position) so shading is continuous across
    # part boundaries, then soften toward world-up (the fighter light rig
    # is top-heavy with a dark 0x4C ambient; vanilla uses hand-tuned soft
    # normals that catch the key light everywhere).
    wkey = {}
    for i, p in enumerate(world):
        k = (round(p[0], 2), round(p[1], 2), round(p[2], 2))
        wkey.setdefault(k, []).append(i)
    wacc = [[0.0, 0.0, 0.0] for _ in world]
    for a, b, c in tris:
        pa, pb, pc = world[a], world[b], world[c]
        e1 = [pb[k]-pa[k] for k in range(3)]
        e2 = [pc[k]-pa[k] for k in range(3)]
        fn = [e1[1]*e2[2]-e1[2]*e2[1], e1[2]*e2[0]-e1[0]*e2[2], e1[0]*e2[1]-e1[1]*e2[0]]
        for i in (a, b, c):
            for k in range(3):
                wacc[i][k] += fn[k]
    wnrm = [None] * len(world)
    for grp in wkey.values():
        sacc = [0.0, 0.0, 0.0]
        for i in grp:
            for k in range(3):
                sacc[k] += wacc[i][k]
        ln = math.sqrt(sum(c*c for c in sacc)) or 1e-9
        sn = [c/ln for c in sacc]
        for i in grp:
            wnrm[i] = sn

    def vnormal(i):
        n = wnrm[i]
        UP_BIAS = 0.0  # obsolete: port now rotates normals per frame
        n = [n[0], n[1] + UP_BIAS, n[2]]
        ln = math.sqrt(sum(c*c for c in n)) or 1e-9
        return [c/ln for c in n]

    out_parts = []
    for joint, rtris in sorted(parts.items()):
        o, R = frames[joint]
        Rinv = inv3(R)
        used = sorted({i for t in rtris for i in t})
        remap = {gi: li for li, gi in enumerate(used)}
        overts = []
        for gi in used:
            pw = part_world(joint, gi)
            d = [pw[k]-o[k] for k in range(3)]
            d = row_apply(d, Rinv)
            sh = vshade(gi)
            r, g, b = (int(c*sh) for c in vcolor(gi)[:3])
            u, vv = uv[gi]
            n = row_apply(vnormal(gi), Rinv)
            nl = math.sqrt(sum(c*c for c in n)) or 1e-9
            overts.append([round(d[0], 2), round(d[1], 2), round(d[2], 2),
                           r, g, b,
                           round(min(1.0, max(0.0, u)), 4),
                           round(min(1.0, max(0.0, vv)), 4),
                           int(sh*255),
                           round(n[0]/nl, 3), round(n[1]/nl, 3), round(n[2]/nl, 3)])
        otris = [[remap[a], remap[b], remap[c]] for a, b, c in rtris]

        # ---- cap open boundary loops: our parts are surface CUTS; at
        # extreme joint angles (tumble, smash) the cuts separate and the
        # open shells read as shredded. Vanilla parts are closed chunks.
        # Fan-cap every boundary loop at its centroid so separated parts
        # stay solid.
        edge_use = {}
        for t in otris:
            for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                key = (min(e), max(e))
                edge_use[key] = edge_use.get(key, 0) + 1
        boundary = {}
        for t in otris:
            for a, b2 in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                if edge_use[(min(a, b2), max(a, b2))] == 1:
                    boundary[a] = b2
        visited = set()
        for start in list(boundary.keys()):
            if start in visited or start not in boundary:
                continue
            loop = [start]
            visited.add(start)
            cur = boundary[start]
            while cur not in visited and cur in boundary and len(loop) < 200:
                loop.append(cur)
                visited.add(cur)
                cur = boundary[cur]
            if len(loop) < 3 or cur != start:
                continue
            # spatial sanity: overlap copies make the merged surface
            # non-manifold, and the edge walker can chain stray interior
            # edges into fake "loops" spanning the whole part — their
            # centroid fans render as long spikes. A real open boundary
            # (pant cuff, wrist, neck cut) has short consecutive edges
            # and a compact radius.
            def _d(i, j2):
                return math.sqrt(sum((overts[i][k]-overts[j2][k])**2 for k in range(3)))
            max_edge = max(_d(loop[k], loop[(k+1) % len(loop)])
                           for k in range(len(loop)))
            if max_edge > 28.0:
                continue
            cx = [sum(overts[i][k] for i in loop)/len(loop) for k in range(3)]
            rad = max(math.sqrt(sum((overts[i][k]-cx[k])**2 for k in range(3)))
                      for i in loop)
            if rad > 55.0:
                continue
            cr = [int(sum(overts[i][k] for i in loop)/len(loop)) for k in (3, 4, 5)]
            # UV: averaging across the ring lands in arbitrary atlas
            # territory (dark wrinkles, other islands) — the "dark crotch
            # tear" artifact. Sample a real loop vertex instead.
            cuv = [overts[loop[0]][6], overts[loop[0]][7]]
            csh = int(sum(overts[i][8] for i in loop)/len(loop))
            cn = [sum(overts[i][k] for i in loop)/len(loop) for k in (9, 10, 11)]
            ci = len(overts)
            overts.append([round(cx[0], 2), round(cx[1], 2), round(cx[2], 2),
                           cr[0], cr[1], cr[2],
                           round(cuv[0], 4), round(cuv[1], 4), csh,
                           round(cn[0], 3), round(cn[1], 3), round(cn[2], 3)])
            for k in range(len(loop)):
                otris.append([loop[k], loop[(k+1) % len(loop)], ci])

        out_parts.append({
            "joint": joint, "region": str(joint), "verts": overts,
            "tris": otris,
        })

    # ---- red-chest rebalance (--redchest): vanilla Mario reads "red
    # chest over a low blue bib"; generated meshes give the bib the whole
    # torso. Locate the buttons (yellow texels -> mesh height), then
    # repaint BLUE texels used by triangles fully ABOVE the buttons to
    # shirt red — the bib visually drops to vanilla's blocking.
    if "--redchest" in sys.argv and img is not None:
        import numpy as _np
        from PIL import ImageDraw as _ImageDraw
        hsvsrc = _np.asarray(img.convert("HSV"), dtype=_np.int16)
        W0, H0 = img.size
        ys = [p[1] for p in pos]
        ymin0, ymax0 = min(ys), max(ys)
        HH = ymax0 - ymin0

        def texel(i):
            u, vv = uv[i]
            x = min(W0-1, max(0, int(u*W0)))
            y = min(H0-1, max(0, int(vv*H0)))
            return hsvsrc[y, x]

        btn_ys = []
        for i in range(0, len(pos), 3):
            h, s2, v2 = texel(i)
            if 25 <= h <= 60 and s2 >= 120 and v2 >= 140:
                btn_ys.append(pos[i][1])
        if btn_ys:
            btn_ys.sort()
            y_btn = btn_ys[len(btn_ys)//2]
            band_lo = y_btn - 0.05 * HH   # red wraps sides/back to waist
            band_hi = y_btn + 0.17 * HH   # stop below the collar/head
            # bib = front-central chest panel below the buttons: stays blue
            ch = [i for i in range(len(pos)) if vpart[i] == 6]
            xs_ch = sorted(pos[i][0] for i in ch)
            zs_ch = sorted(pos[i][2] for i in ch)
            x_mid = xs_ch[len(xs_ch)//2]
            halfw = (xs_ch[-1] - xs_ch[0]) / 2 or 1.0
            z_mid = zs_ch[len(zs_ch)//2]
            mask = Image.new("L", (W0, H0), 0)
            md = _ImageDraw.Draw(mask)
            npaint = 0
            for t in tris:
                if not all(vpart[i] == 6 for i in t):
                    continue
                cy = sum(pos[i][1] for i in t) / 3
                if not (band_lo < cy < band_hi):
                    continue
                cx = sum(pos[i][0] for i in t) / 3
                cz = sum(pos[i][2] for i in t) / 3
                is_bib = (abs(cx - x_mid) < 0.45 * halfw and cz > z_mid
                          and cy < y_btn + 0.02 * HH)
                if is_bib:
                    continue
                md.polygon([(min(W0-1, max(0, uv[i][0]*W0)),
                             min(H0-1, max(0, uv[i][1]*H0))) for i in t],
                           fill=255)
                npaint += 1
            m = _np.asarray(mask) > 0
            hh, ss, vv2 = hsvsrc[...,0], hsvsrc[...,1], hsvsrc[...,2]
            blue = m & (hh >= 120) & (hh <= 185) & (ss >= 60)
            hsv2 = hsvsrc.copy()
            hsv2[...,0][blue] = 4
            hsv2[...,1][blue] = _np.clip(ss[blue]*0.9 + 60, 0, 255)
            hsv2[...,2][blue] = _np.clip(vv2[blue]*1.15 + 10, 0, 255)
            img = Image.fromarray(hsv2.astype(_np.uint8), "HSV").convert("RGB")
            print(f"red-chest: btn_y={y_btn:.3f}, {npaint} tris masked, "
                  f"{int(blue.sum())} blue px -> red")
        else:
            print("red-chest: no yellow button texels found, skipped")

    # ---- hair fix (--brownhair): the generated texture paints the back/
    # side hair mass RED (it reads as a scarf flap in-game and as a red
    # sheet when the head tucks). Vanilla hair below the cap brim is
    # brown: repaint red texels on lower-head triangles, keeping the
    # front brim (over the eyes) red.
    if "--brownhair" in sys.argv and img is not None:
        import numpy as _np3
        from PIL import ImageDraw as _ID3
        W0, H0 = img.size
        hd = [i for i in range(len(pos)) if vpart[i] == 12]
        if hd:
            hy = sorted(pos[i][1] for i in hd)
            hz = sorted(pos[i][2] for i in hd)
            y_cut = hy[0] + 0.45 * (hy[-1] - hy[0])   # below eye level
            z_front = hz[len(hz)//2] + 0.25 * (hz[-1] - hz[0])
            hm = Image.new("L", (W0, H0), 0)
            hmd = _ID3.Draw(hm)
            for t in tris:
                if not all(vpart[i] == 12 for i in t):
                    continue
                cy = sum(pos[i][1] for i in t) / 3
                cz = sum(pos[i][2] for i in t) / 3
                if cy < y_cut and cz < z_front:
                    hmd.polygon([(min(W0-1, max(0, uv[i][0]*W0)),
                                  min(H0-1, max(0, uv[i][1]*H0))) for i in t],
                                fill=255)
            hmask = _np3.asarray(hm) > 0
            hsvH = _np3.asarray(img.convert("HSV"), dtype=_np3.int16)
            hhH, ssH, vvH = hsvH[...,0], hsvH[...,1], hsvH[...,2]
            redH = hmask & (((hhH <= 12) | (hhH >= 243)) & (ssH >= 90))
            hsvH[...,0][redH] = 13                       # hair brown
            hsvH[...,1][redH] = 170
            hsvH[...,2][redH] = _np3.clip(vvH[redH] * 0.55, 45, 115)
            img = Image.fromarray(hsvH.astype(_np3.uint8), "HSV").convert("RGB")
            print(f"brown-hair: {int(redH.sum())} red px -> brown")

    # ---- cap coverage (--capfix): vanilla's cap wraps down the sides of
    # the head; generated heads leave bare temple/side skin above the
    # ears, which reads as flesh gaps through the cap when the head
    # pitches (utilt/usmash tuck). Repaint skin texels in the head's top
    # band to cap red. The face (front) and ears (outermost, lower) are
    # excluded by the band geometry.
    if "--capfix" in sys.argv and img is not None:
        import numpy as _np4
        from PIL import ImageDraw as _ID4
        W0, H0 = img.size
        hd4 = [i for i in range(len(pos)) if vpart[i] == 12]
        if hd4:
            P4 = [(pos[i][0], pos[i][1], pos[i][2]) for i in hd4]
            cx4 = sum(p[0] for p in P4)/len(P4)
            cy4 = sum(p[1] for p in P4)/len(P4)
            cz4 = sum(p[2] for p in P4)/len(P4)
            r4 = sorted(((p[0]-cx4)**2+(p[1]-cy4)**2+(p[2]-cz4)**2)**0.5 for p in P4)
            r4 = r4[len(r4)//2]
            cm = Image.new("L", (W0, H0), 0)
            cmd = _ID4.Draw(cm)
            ncap = 0
            for t in tris:
                if not all(vpart[i] == 12 for i in t):
                    continue
                ccy = sum(pos[i][1] for i in t)/3
                ccx = sum(pos[i][0] for i in t)/3
                if ccy > cy4 - 0.05*r4 and ccx < cx4 + 0.40*r4:
                    cmd.polygon([(min(W0-1, max(0, uv[i][0]*W0)),
                                  min(H0-1, max(0, uv[i][1]*H0))) for i in t],
                                fill=255)
                    ncap += 1
            cmask = _np4.asarray(cm) > 0
            hsvC = _np4.asarray(img.convert("HSV"), dtype=_np4.int16)
            hC, sC, vC = hsvC[...,0], hsvC[...,1], hsvC[...,2]
            skin = cmask & (hC >= 8) & (hC <= 35) & (sC >= 40) & (sC <= 180) & (vC >= 120)
            hsvC[...,0][skin] = 4
            hsvC[...,1][skin] = 215
            hsvC[...,2][skin] = _np4.clip(vC[skin]*0.92, 120, 230)
            img = Image.fromarray(hsvC.astype(_np4.uint8), "HSV").convert("RGB")
            print(f"cap-fix: {ncap} top-band tris, {int(skin.sum())} skin px -> cap red")

    # ---- vanilla flatten (--vanillaflat): N64 fighters use FLAT solid
    # colors; all shading comes from vertex lighting. Rasterize each
    # body texel's 3D position into the atlas (per-texel position map),
    # then paint pixel-straight flat zones: red shirt above the waist
    # wrapping sides/back, flat-blue front bib + overalls below, blue
    # shoulder straps kept, bib-corner buttons added, flat gloves/shoes.
    # Head (part 12) is untouched. Replaces --redchest/--bluelegs.
    # ---- headwear de-bleed (--debleed, general): providers bleed the
    # headwear color into adjacent hair in the bake (red sideburns that
    # read as a flap in motion). Data-driven: cap hue is sampled from
    # the TOP of the head, true hair color from the BACK; lower-head
    # texels matching the cap hue outside the face cone are repainted
    # hair-colored, keeping each texel's V for shading.
    if "--debleed" in sys.argv and img is not None:
        import numpy as _npd
        from PIL import ImageDraw as _IDd
        W0, H0 = img.size
        hd = [i for i in range(len(pos)) if vpart[i] == 12]
        if hd:
            hy = sorted(pos[i][1] for i in hd)
            hx = sorted(pos[i][0] for i in hd)
            y_lo, y_hi = hy[0], hy[-1]
            cap_line = y_lo + 0.62 * (y_hi - y_lo)
            face_x = hx[len(hx)//2] + 0.30 * (hx[-1] - hx[0]) / 2
            def _mask(pred):
                mm = Image.new("L", (W0, H0), 0)
                md = _IDd.Draw(mm)
                for t in tris:
                    if not all(vpart[i] == 12 for i in t):
                        continue
                    cy = sum(pos[i][1] for i in t) / 3
                    cx = sum(pos[i][0] for i in t) / 3
                    if pred(cx, cy):
                        md.polygon([(min(W0-1, max(0, uv[i][0]*W0)),
                                     min(H0-1, max(0, uv[i][1]*H0))) for i in t],
                                   fill=255)
                return _npd.asarray(mm) > 0
            capm = _mask(lambda cx, cy: cy > cap_line)
            backm = _mask(lambda cx, cy: cy < cap_line and cx < face_x - 0.25*(hx[-1]-hx[0]))
            lowm = _mask(lambda cx, cy: cy < cap_line and cx < face_x)
            hsvD = _npd.asarray(img.convert("HSV"), _npd.int16)
            hD, sD, vD = hsvD[...,0], hsvD[...,1], hsvD[...,2]
            print(f"debleed dbg: cap={int(capm.sum())} back={int(backm.sum())} low={int(lowm.sum())}")
            if capm.any() and backm.any():
                capsel = capm & (sD > 60)
                cap_h = int(_npd.median(hD[capsel])) if capsel.any() else -999
                cap_s = int(_npd.median(sD[capsel])) if capsel.any() else 0
                cap_v = int(_npd.median(vD[capsel])) if capsel.any() else 0
                dh = _npd.minimum(_npd.abs(hD - cap_h), 255 - _npd.abs(hD - cap_h))
                # headwear match needs hue AND brightness/sat proximity —
                # hair is often a hue-neighbor (red cap vs brown hair)
                capline = (dh <= 12) & (_npd.abs(sD - cap_s) < 70) & (vD > 0.62 * cap_v)
                hairm = backm & ~capline & (vD > 25)
                print(f"debleed dbg: cap_h={cap_h} hair_px={int(hairm.sum())}")
                if cap_h > -900 and hairm.any():
                    hair_h = int(_npd.median(hD[hairm]))
                    hair_s = int(_npd.median(sD[hairm]))
                    hair_v = float(_npd.median(vD[hairm]))
                    bled = lowm & capline
                    hsvD[...,0][bled] = hair_h
                    hsvD[...,1][bled] = hair_s
                    hsvD[...,2][bled] = _npd.clip(vD[bled] * (hair_v / max(30.0, float(_npd.median(vD[bled])))), 25, 200)
                    img = Image.fromarray(hsvD.astype(_npd.uint8), "HSV").convert("RGB")
                    print(f"debleed: {int(bled.sum())} headwear-hue px on lower head -> hair")

    # ---- source projection (--project-source <img>, general): the
    # provider's texture bake degrades crisp source details (emblems,
    # mustaches, eyes). Rasterize each atlas texel's bind-space position
    # and smooth normal, then re-sample the SOURCE T-pose image
    # orthographically for front-facing texels and blend it over the
    # bake. Character-agnostic: front is auto-detected (+x), the map is
    # bbox-to-bbox, and only non-background source pixels project.
    if project_source_path is not None and img is not None:
        import numpy as _nps
        W0, H0 = img.size
        posm = _nps.zeros((H0, W0, 3), _nps.float32)
        nrmm = _nps.zeros((H0, W0, 3), _nps.float32)
        cov = _nps.zeros((H0, W0), bool)
        NP = _nps.array(nrm, _nps.float32)
        PP = _nps.array(pos, _nps.float32)
        for t in tris:
            xs = _nps.array([uv[i][0]*W0 for i in t]); ysv = _nps.array([uv[i][1]*H0 for i in t])
            x0, x1 = int(max(0, xs.min())), int(min(W0-1, xs.max()))+1
            y0, y1 = int(max(0, ysv.min())), int(min(H0-1, ysv.max()))+1
            if x0 >= x1 or y0 >= y1:
                continue
            gx, gy = _nps.meshgrid(_nps.arange(x0, x1)+0.5, _nps.arange(y0, y1)+0.5)
            d = (xs[1]-xs[0])*(ysv[2]-ysv[0])-(xs[2]-xs[0])*(ysv[1]-ysv[0])
            if abs(d) < 1e-9:
                continue
            w0 = ((xs[1]-gx)*(ysv[2]-gy)-(xs[2]-gx)*(ysv[1]-gy))/d
            w1 = ((xs[2]-gx)*(ysv[0]-gy)-(xs[0]-gx)*(ysv[2]-gy))/d
            w2 = 1-w0-w1
            m = (w0 >= -0.02) & (w1 >= -0.02) & (w2 >= -0.02)
            if not m.any():
                continue
            sl = (slice(y0, y1), slice(x0, x1))
            pp = w0[..., None]*PP[t[0]] + w1[..., None]*PP[t[1]] + w2[..., None]*PP[t[2]]
            nn = w0[..., None]*NP[t[0]] + w1[..., None]*NP[t[1]] + w2[..., None]*NP[t[2]]
            posm[sl][m] = pp[m]; nrmm[sl][m] = nn[m]; cov[sl][m] = True
        src = Image.open(project_source_path).convert("RGB")
        SA = _nps.asarray(src, _nps.float32)
        SH, SW = SA.shape[:2]
        # character mask: pixels far from the border-median background
        bg = _nps.median(_nps.concatenate([SA[0], SA[-1], SA[:, 0], SA[:, -1]]), axis=0)
        charm = (_nps.abs(SA - bg).sum(axis=2) > 60)
        rows = _nps.where(charm.any(axis=1))[0]; cols = _nps.where(charm.any(axis=0))[0]
        sy0, sy1 = int(rows.min()), int(rows.max())
        sx0, sx1 = int(cols.min()), int(cols.max())
        # skeleton-derived axes (any facing): fwd/lat/up from main's triad
        _fw = _nps.array(m_fwd, _nps.float32); _fw /= (_nps.linalg.norm(_fw) + 1e-9)
        _upv = _nps.array(m_upn, _nps.float32); _upv /= (_nps.linalg.norm(_upv) + 1e-9)
        _lt = _nps.cross(_upv, _fw); _lt /= (_nps.linalg.norm(_lt) + 1e-9)
        ycoord = PP @ _upv; lcoord = PP @ _lt
        my0, my1 = float(ycoord.min()), float(ycoord.max())
        ml_mid = float((lcoord.min() + lcoord.max()) / 2)
        s = (sy1 - sy0) / max(1e-6, (my1 - my0))       # px per unit
        sx_mid = (sx0 + sx1) / 2
        nl = _nps.linalg.norm(nrmm, axis=2) + 1e-9
        facing = (nrmm @ _fw) / nl
        wgt = _nps.clip((facing - 0.55) / 0.20, 0, 1) * 0.85
        pl = posm @ _lt; py = posm @ _upv
        # image x runs viewer-left -> right; the character's lateral axis
        # (up x fwd) points to the character's LEFT = viewer's right
        ix = _nps.clip(sx_mid + (pl - ml_mid) * s, 0, SW-1).astype(int)
        iy = _nps.clip(sy1 - (py - my0) * s, 0, SH-1).astype(int)
        inside = charm[iy, ix] & cov & (wgt > 0)
        # depth-select: an orthographic front projection would paint
        # protruding features (nose) onto surfaces behind them. Keep the
        # projection only for texels near the FRONT-MOST depth at their
        # source pixel (coarse source-grid z-buffer).
        CELL = 3
        gx_ = ix // CELL; gy_ = iy // CELL
        gw = SW // CELL + 1
        cell = gy_ * gw + gx_
        depth = posm @ _fw
        zmax = _nps.full(int(cell.max()) + 1, -1e9, _nps.float32)
        _nps.maximum.at(zmax, cell[inside], depth[inside])
        tol = 0.02 * (my1 - my0)
        inside &= depth >= (zmax[cell] - tol)
        out = _nps.asarray(img.convert("RGB"), _nps.float32).copy()
        # detail guard: blend only into locally-FLAT base regions. The
        # bake's own detail (face features) stays; lost details on flat
        # areas (cap emblem, buttons) are restored. Local contrast via a
        # box-blur difference on luminance.
        lum = out.mean(axis=2)
        k = 6
        pad = _nps.pad(lum, k, mode="edge")
        csum = pad.cumsum(0).cumsum(1)
        n = (2*k+1)**2
        box = (csum[2*k:, 2*k:] - csum[:-2*k, 2*k:] - csum[2*k:, :-2*k]
               + csum[:-2*k, :-2*k])[:H0, :W0] / n
        contrast = _nps.abs(lum - box)
        pad2 = _nps.pad(contrast, k, mode="edge")
        csum2 = pad2.cumsum(0).cumsum(1)
        contrast = (csum2[2*k:, 2*k:] - csum2[:-2*k, 2*k:] - csum2[2*k:, :-2*k]
                    + csum2[:-2*k, :-2*k])[:H0, :W0] / n
        flatw = _nps.clip(1.0 - contrast / 18.0, 0.0, 1.0)
        w = (_nps.where(inside, wgt, 0.0) * flatw)[..., None]
        out = out * (1 - w) + SA[iy, ix] * w
        img = Image.fromarray(_nps.clip(out, 0, 255).astype(_nps.uint8), "RGB")
        print(f"project-source: {int(inside.sum())} texels blended from "
              f"{project_source_path}")

    # ---- generic flatten (--flatten, general): providers bake AO and
    # cloth shading into the albedo; N64 fighters are flat colors + a
    # vertex light. Cluster texels into coarse hue/sat/value bins and
    # pull each pixel's V to its bin median (keep hue/sat), removing
    # mottling without any character-specific palette.
    # ---- guided flatten (default for --flatten; --binflat for the old
    # bin-median pull): a self-guided filter on V flattens
    # small-amplitude mottle (baked AO / cloth shading) everywhere while
    # structurally preserving real edges — no bins, no V thresholds, so
    # it cannot draw a contour that isn't in the input. Beat the binned
    # variant 8-2 (14 ties) in the eval/guidedflat blind A/B.
    if "--binflat" not in sys.argv and "--flatten" in sys.argv and img is not None:
        import numpy as _npg
        from scipy.ndimage import uniform_filter as _uf
        hsvG = _npg.asarray(img.convert("HSV"), _npg.uint8).copy()
        I = hsvG[..., 2].astype(_npg.float64) / 255.0
        r = max(8, img.size[0] // 64)          # ~32 texels at 2048
        eps = (14.0 / 255.0) ** 2              # mottle < ~14 V flattens; edges keep
        mI = _uf(I, 2 * r + 1, mode="nearest")
        mII = _uf(I * I, 2 * r + 1, mode="nearest")
        var = _npg.maximum(mII - mI * mI, 0.0)
        A = var / (var + eps)
        B = mI * (1.0 - A)
        q = _uf(A, 2 * r + 1, mode="nearest") * I + _uf(B, 2 * r + 1, mode="nearest")
        hsvG[..., 2] = _npg.clip(q * 255.0, 0, 255).astype(_npg.uint8)
        img = Image.fromarray(hsvG, "HSV").convert("RGB")
        print(f"guided-flat: V guided-filtered (r={r})")
    elif "--flatten" in sys.argv and img is not None:
        import numpy as _npf
        from PIL import ImageFilter as _IF
        hsvF = _npf.asarray(img.convert("HSV"), _npf.int16)
        vF = hsvF[..., 2]
        # bin on a BLURRED copy: JPEG block noise straddling a hard bin
        # edge flips whole 8x8 blocks into the neighbouring (often black)
        # bin — the chunky dark patches on shaded cloth and hair.
        hsvB = _npf.asarray(img.filter(_IF.GaussianBlur(4)).convert("HSV"),
                            _npf.int16)
        hB, sB, vB = hsvB[..., 0], hsvB[..., 1], hsvB[..., 2]
        bins = (_npf.minimum(hB, 254)//16)*100 + (_npf.minimum(sB, 254)//64)*10 + _npf.minimum(vB, 254)//86
        # dark texels are exempt: near black, hue/sat are noise, so the
        # bin splits scatter neighbouring texels across bins with
        # different medians and PAINT patch edges onto smooth hair/pants
        # (boyang's hair blotches). Dark regions never mottle visibly —
        # leave them exactly as authored.
        bins[vB < 70] = -1
        # feathered exemption: a hard V<70 cutoff draws its own contour
        # through shadow gradients (dark blob under the armpit corner).
        # Ramp the pull in from 0 at V=70 to full at V=110 so shadow
        # mid-tones are barely touched and only lit cloth de-mottles.
        ramp = _npf.clip((vB.astype(_npf.float32) - 70.0) / 40.0, 0.0, 1.0)
        outv = vF.astype(_npf.float32)
        for b in _npf.unique(bins):
            if b < 0:
                continue
            m = bins == b
            if m.sum() < 40:
                continue
            med = float(_npf.median(vF[m]))
            # pull weight decays with distance from the bin median: true
            # mottling (small V wobble) flattens hard, while boundary
            # texels that landed in the wrong bin stay put instead of
            # being yanked to a distant median.
            d = vF[m].astype(_npf.float32) - med
            w = 0.75 * _npf.exp(-(d / 30.0)**2) * ramp[m]
            outv[m] = vF[m] + w * (med - vF[m])
        hsvF[..., 2] = _npf.clip(outv, 0, 255).astype(_npf.int16)
        img = Image.fromarray(hsvF.astype(_npf.uint8), "HSV").convert("RGB")
        print("flatten: albedo V pulled to bin medians (soft-binned)")

    if "--vanillaflat" in sys.argv and img is not None:
        import numpy as _npv
        W0, H0 = img.size
        posmap = _npv.zeros((H0, W0, 3), _npv.float32)
        partmap = _npv.full((H0, W0), -1, _npv.int16)
        ys_all = [p[1] for p in pos]
        HH = max(ys_all) - min(ys_all)
        for t in tris:
            pt = max((vpart[i] for i in t), key=lambda q: sum(vpart[i] == q for i in t))
            xs = _npv.array([uv[i][0]*W0 for i in t]); ysv = _npv.array([uv[i][1]*H0 for i in t])
            x0,x1 = int(max(0,xs.min())), int(min(W0-1,xs.max()))+1
            y0,y1 = int(max(0,ysv.min())), int(min(H0-1,ysv.max()))+1
            if x0>=x1 or y0>=y1: continue
            gx,gy = _npv.meshgrid(_npv.arange(x0,x1)+0.5, _npv.arange(y0,y1)+0.5)
            d = (xs[1]-xs[0])*(ysv[2]-ysv[0])-(xs[2]-xs[0])*(ysv[1]-ysv[0])
            if abs(d) < 1e-9: continue
            w0 = ((xs[1]-gx)*(ysv[2]-gy)-(xs[2]-gx)*(ysv[1]-gy))/d
            w1 = ((xs[2]-gx)*(ysv[0]-gy)-(xs[0]-gx)*(ysv[2]-gy))/d
            w2 = 1-w0-w1
            m = (w0>=-0.02)&(w1>=-0.02)&(w2>=-0.02)
            if not m.any(): continue
            pp = (w0[...,None]*_npv.array(pos[t[0]]) + w1[...,None]*_npv.array(pos[t[1]])
                  + w2[...,None]*_npv.array(pos[t[2]]))
            sl = (slice(y0,y1), slice(x0,x1))
            posmap[sl][m] = pp[m]
            partmap[sl][m] = pt
        # palette from the in-game vanilla crop (lit) with V compensation
        try:
            ref = _npv.asarray(Image.open("vanilla-ref-crop.png").convert("HSV"), _npv.int16)
            rh, rs, rvv = ref[...,0], ref[...,1], ref[...,2]
            bm = (rh>=120)&(rh<=185)&(rs>=80)&(rvv>=50)
            rm = ((rh<=12)|(rh>=243))&(rs>=100)&(rvv>=80)
            def med_rgb(mask, vboost):
                hs = int(_npv.median(rh[mask])); ss = int(_npv.median(rs[mask]))
                vs = min(255, int(_npv.median(rvv[mask])*vboost))
                return _npv.array(Image.new("HSV",(1,1),(hs,ss,vs)).convert("RGB").getpixel((0,0)), _npv.float32)
            BLUE = med_rgb(bm, 1.25); RED = med_rgb(rm, 1.18)
        except Exception:
            BLUE = _npv.array([52, 80, 200], _npv.float32); RED = _npv.array([205, 38, 26], _npv.float32)
        GOLD = _npv.array([235, 182, 46], _npv.float32)
        GLOVE = _npv.array([236, 236, 236], _npv.float32)
        SHOE = _npv.array([118, 48, 28], _npv.float32)
        out = _npv.asarray(img.convert("RGB"), _npv.float32).copy()
        X, Y, Z = posmap[...,0], posmap[...,1], posmap[...,2]
        ch = [i for i in range(len(pos)) if vpart[i] == 6]
        zs_ch = sorted(pos[i][2] for i in ch); xs_ch = sorted(pos[i][0] for i in ch)
        z_mid = zs_ch[len(zs_ch)//2]; x_mid = xs_ch[len(xs_ch)//2]
        halfw = (zs_ch[-1]-zs_ch[0])/2 or 1.0
        # waist: reuse button detection (yellow texels -> mesh y) if available
        hsv0 = _npv.asarray(img.convert("HSV"), _npv.int16)
        y_btn = None
        byel = (hsv0[...,0]>=25)&(hsv0[...,0]<=60)&(hsv0[...,1]>=120)&(hsv0[...,2]>=140)&(partmap==6)
        if byel.any():
            y_btn = float(_npv.median(Y[byel]))
        if y_btn is None:
            y_btn = min(ys_all) + 0.43*HH
        LEGS = (partmap==19)|(partmap==20)|(partmap==24)|(partmap==25)
        CHEST = partmap==6
        ARMS = (partmap==8)|(partmap==9)|(partmap==14)|(partmap==15)
        HANDS = (partmap==10)|(partmap==16)
        FEET = (partmap==22)|(partmap==27)
        is_bib = CHEST & (X > x_mid) & (_npv.abs(Z - z_mid) < 0.45*halfw) & (Y < y_btn + 0.02*HH)
        red_zone = CHEST & (Y > y_btn - 0.05*HH) & ~is_bib
        # shoe/leg boundary by clean height, not jagged part-id edges
        y_ankle = min(ys_all) + 0.105*HH
        shoe_zone = (LEGS | FEET) & (Y < y_ankle)
        blue_zone = ((CHEST & ~red_zone) | LEGS) & ~shoe_zone
        out[red_zone] = RED
        out[blue_zone] = BLUE
        out[ARMS] = RED
        out[HANDS] = GLOVE
        out[FEET & ~shoe_zone] = SHOE
        out[shoe_zone] = SHOE
        # bib-corner buttons (vanilla placement)
        for zoff in (-0.34*halfw, 0.34*halfw):
            corner = _npv.array([xs_ch[-1], y_btn, z_mid+zoff], _npv.float32)
            dd2 = (X-corner[0])**2*0.25 + (Y-corner[1])**2 + (Z-corner[2])**2
            out[(dd2 < (0.030*HH)**2) & (CHEST)] = GOLD
        img = Image.fromarray(_npv.clip(out,0,255).astype(_npv.uint8), "RGB")
        print(f"vanilla-flat: waist y={y_btn:.3f}, red {int(red_zone.sum())} px, "
              f"blue {int(blue_zone.sum())} px")

    # ---- leg cleanup (--bluelegs): kill hallucinated red seams inside
    # the trouser legs (generated textures sometimes paint a red crotch/
    # inner-seam streak). Mask = UV triangles whose verts are all
    # leg-part dominant; red texels inside go to the median pants blue.
    if "--bluelegs" in sys.argv and img is not None:
        import numpy as _np2
        from PIL import ImageDraw as _ID2
        W0, H0 = img.size
        legmask = Image.new("L", (W0, H0), 0)
        ld = _ID2.Draw(legmask)
        LEGS = {19, 20, 24, 25}
        # crotch zone: chest-part tris in the lower belly also bleed the
        # red seam; include them (feet stay excluded — shoes are red).
        ys2 = [p[1] for p in pos]
        y_lo = min(ys2) + 0.38 * (max(ys2) - min(ys2))
        for t in tris:
            in_legs = all(vpart[i] in LEGS for i in t)
            in_crotch = all(vpart[i] == 6 and pos[i][1] < y_lo for i in t)
            if in_legs or in_crotch:
                ld.polygon([(min(W0-1, max(0, uv[i][0]*W0)),
                             min(H0-1, max(0, uv[i][1]*H0))) for i in t], fill=255)
        lm = _np2.asarray(legmask) > 0
        hsvL = _np2.asarray(img.convert("HSV"), dtype=_np2.int16)
        hhL, ssL, vvL = hsvL[...,0], hsvL[...,1], hsvL[...,2]
        redL = lm & (((hhL <= 12) | (hhL >= 243)) & (ssL >= 90))
        blueL = lm & (hhL >= 120) & (hhL <= 185) & (ssL >= 60)
        if redL.any() and blueL.any():
            bh = int(_np2.median(hhL[blueL])); bs = int(_np2.median(ssL[blueL])); bv = int(_np2.median(vvL[blueL]))
            hsvL[...,0][redL] = bh; hsvL[...,1][redL] = bs; hsvL[...,2][redL] = bv
            img = Image.fromarray(hsvL.astype(_np2.uint8), "HSV").convert("RGB")
            print(f"blue-legs: {int(redL.sum())} red px -> pants blue")

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
        # vibrance: vanilla N64 fighters are saturated flat-color materials;
        # Meshy albedo is comparatively muted. Mild S/V boost in HSV.
        out_img = Image.fromarray(arr.astype(np.uint8)).resize(
            (1024, 1024), Image.LANCZOS)
        if "--mild-color" in sys.argv:
            out_img.save(atlas_path)
        else:
            hsv = np.asarray(out_img.convert("HSV"), dtype=np.float32)
            hsv[..., 1] = np.clip(hsv[..., 1] * 1.18, 0, 255)
            hsv[..., 2] = np.clip(hsv[..., 2] * 1.16, 0, 255)
            Image.fromarray(hsv.astype(np.uint8), "HSV").convert("RGB").save(atlas_path)

    # ---- OSB5 skinned payload: the WHOLE mesh, un-chopped. Vertices in
    # spawn-world space (the LBS-authored `world`), weights over mario
    # part joints, plus uv/normals. The game CPU-skins this each frame —
    # true smooth deformation, no part seams at all.
    sk_joint_ids = sorted({p for vw in vweights for p in vw})
    # cap claim: crown verts partially weighted to neck/chest stretch the
    # cap into a "sail" when the head pitches (utilt/usmash). Anything in
    # the top band of the mesh that already leans Head goes 100% Head.
    ys_sk = [p[1] for p in pos]
    H_sk = max(ys_sk) - min(ys_sk)
    hj = jpos[names.index("Head")] if "Head" in names else None
    neck_y_sk = jpos[names.index("neck")][1] if "neck" in names else (min(ys_sk) + 0.6*H_sk)
    n_capped = 0
    _claimed = set()      # verts the cap/arm claims re-leaned (see freeze)
    ARMISH = ("ForeArm", "Hand")
    for i in range(len(world)):
        if hj is None: break
        jb = names[jix[i][max(range(4), key=lambda k: wts[i][k])]]
        if any(a in jb for a in ARMISH):
            continue   # sleeve/glove verts sit in the head shell on chibi
        d2 = sum((pos[i][k]-hj[k])**2 for k in range(3))
        if d2 < (0.42*H_sk)**2 and pos[i][1] > neck_y_sk + 0.01*H_sk:
            if abs(vweights[i].get(12, 0.0) - 1.0) > 1e-6:
                vweights[i] = {12: 1.0}
                _claimed.add(i)
                n_capped += 1
    if n_capped:
        print(f"cap claim: {n_capped} crown verts -> 100% Head")
    # arm claim (general): providers rig loose sleeves to the SPINE (and
    # draped hair to the head), so the geometry occupying the arm region
    # stays glued to the torso while only the gloves follow the hands —
    # invisible on mild Mario poses, glaring on targets whose animations
    # throw the arms wide (Samus's crouch: gloves fly, no arm follows).
    # Any vert inside a T-pose arm-bone capsule, clear of the chest,
    # whose weights lean torso/neck/head gets re-leaned onto that arm
    # bone's part (blended, so claim boundaries still deform smoothly).
    n_armed = 0
    for _pref in (posx, negx):
        for _seg0, _seg1 in ((_pref + "Arm", _pref + "ForeArm"),
                             (_pref + "ForeArm", _pref + "Hand")):
            if _seg0 not in name_idx or _seg1 not in name_idx or _seg0 not in bone_map:
                continue
            _a = jpos[name_idx[_seg0]]
            _b = jpos[name_idx[_seg1]]
            _part = bone_map[_seg0][0]
            _ab = [_b[k] - _a[k] for k in range(3)]
            _ab2 = sum(c * c for c in _ab) or 1e-9
            _blen = _ab2 ** 0.5
            # lateral = the arm bone's own direction (this runs in T-pose,
            # so the bone IS the lateral axis) — measuring against world x
            # broke on rigs whose arms lie along z (tripo): the chest gate
            # went to ~0 and boyang's sleeve claim collapsed to 4 verts
            _u = [c / _blen for c in _ab]
            _ctr = jpos[name_idx["Spine02"]] if "Spine02" in name_idx else _a
            _sh_lat = sum((_a[k] - _ctr[k]) * _u[k] for k in range(3))
            # per-dominance radius: chest/neck-owned verts inside the axial
            # span are sleeve by construction (the torso silhouette cannot
            # reach past the shoulder in a T-pose), and chibi sleeves bulge
            # to ~2.2x a stubby arm bone — but hair overhanging the
            # shoulders occupies the same band, so head-owned verts keep
            # the tight capsule
            _r2_torso = (2.4 * _blen) ** 2
            _r2_head = (0.72 * _blen) ** 2
            _dbg = __import__('os').environ.get('SSB64_CLAIM_DEBUG')
            _rej = {'lat': 0, 't': 0, 'r': 0, 'dom': 0, 'ok': 0}
            for i in range(len(world)):
                _lat = sum((pos[i][k] - _ctr[k]) * _u[k] for k in range(3))
                if _lat < 0.6 * _sh_lat:
                    _rej['lat'] += 1
                    continue   # chest-side verts stay with the torso
                _t = sum((pos[i][k] - _a[k]) * _ab[k] for k in range(3)) / _ab2
                if _t < -0.1 or _t > 1.1:
                    _rej['t'] += 1
                    continue
                _dom = max(vweights[i].items(), key=lambda kv: kv[1])[0]
                # graded is the default since the 2026-08-28 blind eval
                # (1-0-23 vs flat; flat hardening had lost 0-11-13)
                _graded = not ({"--flat-armclaim", "--base-recipe"} & set(sys.argv))
                _armdom = _dom in (8, 9, 10, 14, 15, 16)
                if _dom not in (6, 7, 11, 12, 13) and not (_graded and _armdom):
                    _rej['dom'] += 1
                    continue
                _q = [_a[k] + max(0.0, min(1.0, _t)) * _ab[k] for k in range(3)]
                _r2 = _r2_head if _dom in (12, 13) else _r2_torso
                if sum((pos[i][k] - _q[k]) ** 2 for k in range(3)) > _r2:
                    _rej['r'] += 1
                    continue
                _rej['ok'] += 1
                _claimed.add(i)
                if TARGET_TUNE.get("rigid_arms"):
                    _g = 0.95
                    _mix = {p: (1.0 - _g) * w for p, w in vweights[i].items()
                            if p != _part}
                    _mix[_part] = _g + (1.0 - _g) * vweights[i].get(_part, 0.0)
                elif _graded:
                    # ownership ramps along the bone (classic skinning
                    # falloff): the shoulder end keeps blending with the
                    # chest so the deltoid deforms smoothly, the distal
                    # end is owned outright so the tube TRAVELS with the
                    # arm instead of collapsing to a smear edge. Flat
                    # hardening lost the 2026-08-28 blind eval (0-11-13:
                    # skinny rigid tube on samus, seams on luigi/link).
                    _g = 0.45 + 0.5 * max(0.0, min(1.0, _t))
                    _mix = {p: (1.0 - _g) * w for p, w in vweights[i].items()
                            if p != _part}
                    _mix[_part] = _g + (1.0 - _g) * vweights[i].get(_part, 0.0)
                else:
                    _mix = {p: 0.25 * w for p, w in vweights[i].items()}
                    _mix[_part] = _mix.get(_part, 0.0) + 0.75
                _tt = sum(_mix.values()) or 1.0
                vweights[i] = {p: w / _tt for p, w in
                               sorted(_mix.items(), key=lambda kv: -kv[1])[:4]}
                n_armed += 1
            if _dbg:
                print(f"  claim-debug {_seg0}->{_seg1}: blen={_blen:.3f} "
                      f"sh_lat={_sh_lat:.3f} rej={_rej}")
    if n_armed:
        print(f"arm claim: {n_armed} sleeve/shoulder verts re-leaned onto arm bones")
    # ---- post-claim weight re-smoothing (general): the cap/arm claims
    # above assign flat weights (crown -> {12:1.0}, sleeves -> 0.75 arm),
    # punching hard cliffs into the diffused part-weight field. A vert
    # anchored 100% Head sitting one edge away from an arm-anchored vert
    # shears that triangle into a zero-volume fin whenever the animation
    # rotates the joints apart — the run cycle's arm swing + torso lean
    # made fins jut from the shoulder/collar on EVERY character. Re-diffuse
    # over the welded graph so every claim boundary blends over a band
    # (interiors are untouched: a vert whose neighbours agree keeps its
    # weights). Offline replay of dumped run/fall/landing joint frames:
    # p99.9 triangle stretch 6.9x -> 3.1x, tris past 3x 79 -> 5.
    _cur = {r: dict(vweights[r]) for r in _adj} if "--no-postsmooth" not in sys.argv else {}
    # anatomical guard: a vert may only GAIN weight on parts skeleton-
    # adjacent to ones it starts with (PART_ADJ). Unguarded, the 4-hop
    # diffusion walks arm weight through the collar into the face on
    # short-necked meshes and every arm move drags the face laterally.
    # blind eval 2026-08-28 (eval/guard, 24 pairs): unguarded won 15-0-9 —
    # the diffusion's anatomically-wrong blends still LOOK better in play
    # than the fins they prevent. Guard kept opt-in for A/Bs until the
    # mis-rigged-vert root cause is fixed; it does bring back the Moritz
    # face drag (arm weight walks through the collar into the face).
    _guard = "--adjguard" in sys.argv
    _ok = ({r: set(w) | set().union(*(PART_ADJ.get(p, set()) for p in w))
            for r, w in _cur.items()} if _guard else {})
    # profile tune "postsmooth_iters": crush-class targets (pikachu) have
    # far bigger inter-part transform disagreement, so claim cliffs shear
    # harder in motion — deeper diffusion widens the blend bands.
    _ps_iters = int(TARGET_TUNE.get("postsmooth_iters", 4))
    # --claim-freeze: claimed verts act as fixed boundary conditions in
    # the diffusion — they still feed their neighbors, but their own
    # weights never update. Without this the 4 iterations dilute the arm
    # claim's 0.75 leans back to ~0.5 (326/342 arm verts soft, measured
    # 2026-08-28) and the sleeve smears off the bone on wide-swing
    # targets (samus).
    # (rigid_arms deliberately does NOT freeze: a 0.95 cliff with no
    # diffusion shears the boundary tris open — holes across the torso.
    # With the whole tube claimed high, diffusion leaves the interior
    # alone and only softens the boundary into a narrow band.)
    _frozen = ({_rep[i] for i in _claimed}
               if "--claim-freeze" in sys.argv else set())
    for _it in range(_ps_iters if _cur else 0):
        _nxt = {}
        for r, nbrs in _adj.items():
            if r in _frozen:
                _nxt[r] = _cur[r]
                continue
            acc2 = {p: 0.5 * w for p, w in _cur[r].items()}
            share = 0.5 / len(nbrs)
            for nb in nbrs:
                for p, w in _cur[nb].items():
                    if not _guard or p in _ok[r]:
                        acc2[p] = acc2.get(p, 0.0) + share * w
            top = sorted(acc2.items(), key=lambda kv: -kv[1])[:4]
            tot = sum(w for _, w in top) or 1.0
            _nxt[r] = {p: w / tot for p, w in top if w / tot > 0.02}
        _cur = _nxt
    for _i in range(len(world)):
        r = _rep[_i]
        if r in _cur and _cur[r]:
            vweights[_i] = dict(_cur[r])
            vpart[_i] = max(vweights[_i], key=vweights[_i].get)
    # re-apply the midline purge: diffusion across touching mirror limbs
    # (welded shoes/thighs) would otherwise re-introduce cross-leg slivers.
    n_purged2 = 0
    for _i in (range(len(world)) if _cur else ()):
        vw = vweights[_i]
        if not any(p in vw and _MIR.get(p) in vw for p in vw):
            continue
        lsum = sum(w for p, w in vw.items() if p in _LEFTS)
        rsum = sum(w for p, w in vw.items() if _MIR.get(p) in _LEFTS)
        drop = (_LEFTS if lsum < rsum else {_MIR[p] for p in _LEFTS})
        vw2 = {p: w for p, w in vw.items() if p not in drop}
        tot = sum(vw2.values()) or 1.0
        vweights[_i] = {p: w / tot for p, w in vw2.items()}
        vpart[_i] = max(vweights[_i], key=vweights[_i].get)
        n_purged2 += 1
    if _cur:
        print(f"post-claim weight smoothing: claim boundaries re-diffused"
              + (f", {n_purged2} cross-side verts re-purged" if n_purged2 else ""))
    # profile tune "rigid_legs": collapse each leg chain (calf/foot -> thigh
    # part) so the whole leg rides ONE joint. Crush-class targets (pikachu)
    # give thigh/calf/foot wildly disagreeing transforms; blending across
    # them turns the run gallop's legs to rubber. A rigid stubby leg
    # pivoting at the hip matches the vanilla fighter's own proportions.
    if TARGET_TUNE.get("rigid_arms"):
        _ARMC = {9: 8, 10: 8, 15: 14, 16: 14}
        for _r, _kids in (("8", (8, 9, 10)), ("14", (14, 15, 16))):
            if TARGET_TUNE.get("arm_anchor", {}).get(_r) == "distal":
                # split: upper stub keeps its own joint, forearm+hand
                # ride the distal (cannon) joint as the second segment
                _ARMC.pop(_kids[1], None)
                _ARMC.pop(_kids[0], None)
                _ARMC[_kids[1]] = _kids[2]
        n_ra = 0
        for _i in range(len(world)):
            vw = vweights[_i]
            if not any(p in _ARMC for p in vw):
                continue
            vw2 = {}
            for p, w in vw.items():
                q = _ARMC.get(p, p)
                vw2[q] = vw2.get(q, 0.0) + w
            vweights[_i] = vw2
            vpart[_i] = max(vw2, key=vw2.get)
            n_ra += 1
        print(f"rigid arms: {n_ra} verts' forearm/hand weights collapsed onto shoulders")
    if TARGET_TUNE.get("rigid_legs"):
        _LEGC = {20: 19, 22: 19, 25: 24, 27: 24}
        n_rl = 0
        for _i in range(len(world)):
            vw = vweights[_i]
            if not any(p in _LEGC for p in vw):
                continue
            vw2 = {}
            for p, w in vw.items():
                q = _LEGC.get(p, p)
                vw2[q] = vw2.get(q, 0.0) + w
            vweights[_i] = vw2
            vpart[_i] = max(vw2, key=vw2.get)
            n_rl += 1
        print(f"rigid legs: {n_rl} verts' calf/foot weights collapsed onto thighs")
        # side-coherence relaxation: per-vert geometric side assignment is
        # noisy on fused inner thighs, so speckled L/R thigh weights shear
        # the leg into lumps once the gallop separates the legs. Relax each
        # leg vert's side toward its welded neighbours' majority, with the
        # geometric side (lateral offset from the hip axis) as a prior —
        # the genuine split survives at the midline, the speckle dies.
        try:
            _pLu = jpos[name_idx[posx + "UpLeg"]]
            _pRu = jpos[name_idx[negx + "UpLeg"]]
            _latu = [_pLu[k] - _pRu[k] for k in range(3)]
            _latL2 = math.sqrt(sum(c * c for c in _latu)) or 1e-9
            _midu = [(_pLu[k] + _pRu[k]) / 2 for k in range(3)]
            _legset = [i for i in range(len(world))
                       if vweights[i].get(19, 0.0) + vweights[i].get(24, 0.0) > 0.0]
            _side = {}
            _prior = {}
            for i in _legset:
                _side[i] = 1.0 if vweights[i].get(19, 0.0) >= vweights[i].get(24, 0.0) else -1.0
                _prior[i] = max(-1.0, min(1.0, sum(
                    (pos[i][k] - _midu[k]) * _latu[k] for k in range(3)) / (0.25 * _latL2 * _latL2)))
            for _it in range(8):
                _ns = {}
                for i in _legset:
                    r = _rep[i]
                    nb = [j for j in _adj.get(r, ())]
                    m = sum(_side.get(j, 0.0) for j in nb) / (len(nb) or 1)
                    v = 0.6 * m + 0.4 * _prior[i]
                    _ns[i] = 1.0 if v >= 0 else -1.0
                _side = _ns
            n_flip = 0
            for i in _legset:
                want19 = _side[i] > 0
                w19 = vweights[i].get(19, 0.0)
                w24 = vweights[i].get(24, 0.0)
                if (w19 >= w24) == want19:
                    continue
                vw = dict(vweights[i])
                vw[19 if want19 else 24] = w19 + w24
                vw.pop(24 if want19 else 19, None)
                if not want19 and 19 in vw:
                    vw.pop(19, None)
                vweights[i] = vw
                vpart[i] = max(vw, key=vw.get)
                n_flip += 1
            if n_flip:
                print(f"rigid legs: side relaxation flipped {n_flip} speckled thigh verts")
        except (KeyError, IndexError):
            pass
    # cap shrinkwrap: the generated cap flares out well past the skull
    # sphere at the sides/back; pitched with the head (utilt/usmash) the
    # flare sweeps out as a big red "sail". Pull back/side cap verts that
    # sit far outside the median head radius toward the skull. The front
    # brim (over the eyes) keeps its protrusion.
    if hj is not None and "--shrinkwrap" in sys.argv:
        # NOTE: regressed r21 (spiky brim edge — clamped verts alternate
        # with spared neighbors). Keep off unless smoothed.
        import numpy as _npc
        hv = [i for i in range(len(world))
              if vweights[i] == {12: 1.0} or (len(vweights[i]) == 1 and abs(vweights[i].get(12,0)-1.0) < 1e-6)]
        if len(hv) > 50:
            P = _npc.array([pos[i] for i in hv])
            Wd = _npc.array([world[i] for i in hv])
            c = P.mean(0)
            r = _npc.linalg.norm(P - c, axis=1)
            r_med = float(_npc.median(r))
            # rigid bind->spawn transform for the head (Kabsch)
            Pc, Wc = P - P.mean(0), Wd - Wd.mean(0)
            U, S, Vt = _npc.linalg.svd(Pc.T @ Wc)
            d = _npc.sign(_npc.linalg.det(Vt.T @ U.T))
            R = Vt.T @ _npc.diag([1, 1, d]) @ U.T
            t = Wd.mean(0) - R @ P.mean(0)
            LIM = 1.12 * r_med
            n_wrap = 0
            for k, i in enumerate(hv):
                pvec = P[k] - c
                rr = float(_npc.linalg.norm(pvec))
                if rr > LIM and pvec[0] < 0.15 * r_med:   # not the front brim (+x = face)
                    p2 = c + pvec * (LIM / rr)
                    pos[i] = tuple(p2)
                    world[i] = tuple(R @ p2 + t)
                    n_wrap += 1
            if n_wrap:
                print(f"cap shrinkwrap: {n_wrap} flare verts pulled to {LIM:.3f} "
                      f"(median head radius {r_med:.3f})")
    # ---- RIGID PARTS (general, default): build the fighter the way
    # vanilla fighters are built. A connected skinned mesh MUST stretch
    # triangles that span a joint when the limb swings (rear-shoulder
    # flaps at the taunt, wedge arms in smashes); rigid overlapping parts
    # never stretch — they rotate and interpenetrate. Each vertex goes
    # 100% to its dominant part; every joint-spanning triangle is
    # duplicated into BOTH parts (one ring of overlap); each part's open
    # boundary rings at joints are fan-capped so the pieces are closed.
    rigid_world, rigid_uv, rigid_n, rigid_w, rigid_tris = [], [], [], [], []
    if "--rigid" in sys.argv:   # experimental: rigid overlapping parts (rejected in play — stays opt-in)
        dom = [max(vweights[i], key=vweights[i].get) for i in range(len(world))]
        copies = {}   # (orig vert, part) -> new index
        def _copy(i, part):
            key = (i, part)
            if key not in copies:
                copies[key] = len(rigid_world)
                rigid_world.append(world[i]); rigid_uv.append(uv[i]); rigid_n.append(vnormal(i))
                rigid_w.append({part: 1.0})
            return copies[key]
        part_tris = {}
        for t in tris:
            parts_here = {dom[i] for i in t}
            for part in parts_here:          # mixed tris -> duplicated into every part touched (overlap)
                nt = tuple(_copy(i, part) for i in t)
                rigid_tris.append(nt); part_tris.setdefault(part, []).append(nt)
        # caps: boundary loops per part (edges used once within the part)
        import collections as _cl
        H_r = max(p[1] for p in pos) - min(p[1] for p in pos)
        n_caps = 0; n_cap_tris = 0
        for part, plist in part_tris.items():
            ecount = _cl.Counter()
            for a_, b_, c_ in plist:
                for e in ((a_, b_), (b_, c_), (c_, a_)):
                    ecount[tuple(sorted(e))] += 1
            bedges = [e for e, n in ecount.items() if n == 1]
            nbr = _cl.defaultdict(list)
            for a_, b_ in bedges:
                nbr[a_].append(b_); nbr[b_].append(a_)
            seen = set()
            for start in list(nbr):
                if start in seen or len(nbr[start]) != 2:
                    continue
                loop = [start]; prev = None; cur = start
                while True:
                    seen.add(cur)
                    nxt = [x for x in nbr[cur] if x != prev]
                    if not nxt: break
                    nx = nxt[0]
                    if nx == start: break
                    if nx in seen: break
                    loop.append(nx); prev, cur = cur, nx
                if len(loop) < 3:
                    continue
                # spatial sanity in WORLD units relative to height: a joint
                # ring is compact; reject sprawling fake loops
                P_ = [rigid_world[i] for i in loop]
                cen = [sum(q[k] for q in P_) / len(P_) for k in range(3)]
                rad = max(math.dist(q, cen) for q in P_)
                emax = max(math.dist(rigid_world[loop[i]], rigid_world[loop[(i + 1) % len(loop)]]) for i in range(len(loop)))
                if rad > 0.22 * (max(w_[1] for w_ in world) - min(w_[1] for w_ in world)) or emax > 0.12 * (max(w_[1] for w_ in world) - min(w_[1] for w_ in world)):
                    continue
                ci = len(rigid_world)
                rigid_world.append(tuple(cen)); rigid_uv.append(rigid_uv[loop[0]])
                nsum = [sum(rigid_n[i][k] for i in loop) for k in range(3)]
                nl_ = math.sqrt(sum(c * c for c in nsum)) or 1e-9
                rigid_n.append([c / nl_ for c in nsum]); rigid_w.append({part: 1.0})
                for i in range(len(loop)):
                    rigid_tris.append((loop[i], loop[(i + 1) % len(loop)], ci)); n_cap_tris += 1
                n_caps += 1
        print(f"rigid parts: {len(rigid_world)} verts ({len(world)} orig), {len(rigid_tris)} tris, "
              f"{n_caps} joint caps ({n_cap_tris} tris)")
        world = rigid_world; uv = rigid_uv; vweights = rigid_w; tris = [list(t) for t in rigid_tris]
        pos = [pos[0]] * 0 or pos   # bind pos no longer aligned; stretch test below is skipped for rigid
        _rigid_done = True
    else:
        _rigid_done = False

    # (sk_verts is emitted AFTER the weld/cut passes below so the blended
    #  weights and closed gaps actually reach the bundle)
    # degenerate-connectivity filter (general): providers occasionally
    # emit long internal bridge triangles (fused-limb webbing, remesh
    # artifacts). Real surface edges on these meshes are a few percent
    # of model height in BIND space; anything an order beyond that is
    # garbage that tears into slivers when posed. Cut by bind length.
    # Criterion: STRETCH ratio. A triangle the retarget tore has a
    # world edge far longer than its bind edge times the global scale;
    # big flat low-poly panels (long bind edges) are legitimate and are
    # kept. Drop only if some edge stretched > 3x.
    # ---- seam weld (general): extreme target poses (DK's 90-degree hip
    # flexion) pull apart mesh edges that cross ADJACENT parts (skirt hem
    # between torso and thighs). Cutting those makes holes; instead weld:
    # blend the two verts' part weights toward each other (they then move
    # together in every pose) and close most of the bind-position gap.
    # Non-adjacent crossings (hand-to-hip webbing) stay cut below.
    _ADJ = set()
    for _pa, _ch in ((6, 19), (6, 24), (6, 8), (6, 14), (6, 11), (11, 12),
                     (8, 9), (9, 10), (14, 15), (15, 16),
                     (19, 20), (20, 22), (24, 25), (25, 27), (6, 12)):
        _ADJ.add(frozenset((_pa, _ch)))
    _welded = 0
    _welded_verts = set()
    # degenerate-mapping guard (same rationale as the torn-edge weld guard
    # below): on crush-class targets (Kirby/Purin-style, whole humanoid
    # onto 1-2 joints) cross-part stretch is pervasive and welding pulls
    # the entire mesh into itself until it is invisible. Weld only when
    # tears are LOCAL.
    _cross_torn = 0
    for t in tris:
        for a2, b2 in ((t[0], t[1]), (t[1], t[2]), (t[0], t[2])):
            pa_, pb_ = vpart[a2], vpart[b2]
            if pa_ == pb_ or frozenset((pa_, pb_)) not in _ADJ:
                continue
            db = sum((pos[a2][k] - pos[b2][k]) ** 2 for k in range(3)) ** 0.5
            dw = sum((world[a2][k] - world[b2][k]) ** 2 for k in range(3)) ** 0.5
            if dw > 2.5 * max(db, 0.01) * s_perp and dw > 0.06 * s_perp:
                _cross_torn += 1
    # profile tune "force_seam_weld": crush-class targets trip the global-
    # crush guard by definition, but with rigid_legs the tears really are
    # local (part boundaries only) — welding closes the zero-volume fins
    # that neither cutting (holes) nor keeping (flat flaps) can fix.
    if _cross_torn > max(120, int(0.05 * len(tris))) and not TARGET_TUNE.get("force_seam_weld"):
        print(f"seam weld: skipped ({_cross_torn} torn cross-part edges is "
              f"global crush, not local seams)")
    else:
     for _pass in range(2):
        for t in tris:
            for a2, b2 in ((t[0], t[1]), (t[1], t[2]), (t[0], t[2])):
                pa_, pb_ = vpart[a2], vpart[b2]
                if pa_ == pb_ or frozenset((pa_, pb_)) not in _ADJ:
                    continue
                db = sum((pos[a2][k] - pos[b2][k]) ** 2 for k in range(3)) ** 0.5
                dw = sum((world[a2][k] - world[b2][k]) ** 2 for k in range(3)) ** 0.5
                if dw <= 2.5 * max(db, 0.01) * s_perp or dw <= 0.06 * s_perp:
                    continue
                # blend part weights 70/30 toward each other
                for i_, j_ in ((a2, b2), (b2, a2)):
                    mix = {}
                    for p_, w_ in vweights[i_].items():
                        mix[p_] = mix.get(p_, 0.0) + 0.7 * w_
                    for p_, w_ in vweights[j_].items():
                        mix[p_] = mix.get(p_, 0.0) + 0.3 * w_
                    tot = sum(mix.values()) or 1.0
                    vweights[i_] = {p_: w_ / tot for p_, w_ in
                                    sorted(mix.items(), key=lambda kv: -kv[1])[:4]}
                # close 70% of the world gap symmetrically
                mid = [(world[a2][k] + world[b2][k]) * 0.5 for k in range(3)]
                world[a2] = tuple(world[a2][k] + 0.85 * (mid[k] - world[a2][k]) for k in range(3))
                world[b2] = tuple(world[b2][k] + 0.85 * (mid[k] - world[b2][k]) for k in range(3))
                _welded += 1
                _welded_verts.add(a2); _welded_verts.add(b2)
    if _welded:
        print(f"seam weld: {_welded} cross-part edges closed instead of cut")

    # The cut threshold is RELATIVE to the median edge stretch: on extreme
    # target skeletons (DK's gorilla arms) the legitimate baseline stretch
    # is itself ~3x, and an absolute threshold deletes valid geometry.
    # baseline per PART: a gorilla-armed target stretches whole limbs
    # legitimately; a global median (torso-dominated) misses that.
    _part_ratios = {}
    for t in tris:
        pr = vpart[t[0]]
        for a2, b2 in ((t[0], t[1]), (t[1], t[2]), (t[0], t[2])):
            db = sum((pos[a2][k] - pos[b2][k]) ** 2 for k in range(3)) ** 0.5
            dw = sum((world[a2][k] - world[b2][k]) ** 2 for k in range(3)) ** 0.5
            if db > 1e-6:
                _part_ratios.setdefault(pr, []).append(dw / (db * s_perp))
    _part_med = {}
    for pr, rs in _part_ratios.items():
        rs.sort()
        _part_med[pr] = rs[len(rs) // 2]
    def _cut_for(t):
        m = max(_part_med.get(vpart[i], 1.0) for i in t)
        return max(3.0, 3.0 * m)
    # torn-edge weld (general): a torn edge INSIDE a part (or across
    # adjacent parts) is real surface whose endpoint weights diverged —
    # coat verts sharing torso+arm influence tear when the target's
    # proportions separate those joints. Cutting leaves visible holes
    # (exposed once the vanilla body underneath is blanked); instead give
    # both endpoints the same averaged weights so the edge moves as one,
    # and close the world gap. Non-adjacent-part bridges (hand-to-hip
    # webbing) are garbage and still get cut below.
    _torn_welded = 0
    # degenerate-mapping guard: when torn edges are pervasive (crush-class
    # targets like Kirby, where a whole humanoid maps onto 1-2 joints),
    # welding averages weights across the entire mesh and collapses it to
    # a point. Welding is for LOCAL tears; if more than ~5% of the mesh is
    # "torn", the stretch is global and legitimate — keep the mesh as-is.
    _torn_edge_count = 0
    if not _rigid_done:
        for t in tris:
            _cut = _cut_for(t)
            for a2, b2 in ((t[0], t[1]), (t[1], t[2]), (t[0], t[2])):
                pa_, pb_ = vpart[a2], vpart[b2]
                if pa_ != pb_ and frozenset((pa_, pb_)) not in _ADJ:
                    continue
                db = sum((pos[a2][k] - pos[b2][k]) ** 2 for k in range(3)) ** 0.5
                dw = sum((world[a2][k] - world[b2][k]) ** 2 for k in range(3)) ** 0.5
                if dw > _cut * max(db, 0.01) * s_perp and dw > 0.06 * s_perp:
                    _torn_edge_count += 1
    _torn_weld_ok = (_torn_edge_count <= max(60, int(0.05 * len(tris)))
                     or bool(TARGET_TUNE.get("force_seam_weld")))
    if not _torn_weld_ok and _torn_edge_count:
        print(f"torn-edge weld: skipped ({_torn_edge_count} torn edges is "
              f"global crush, not local tears)")
    if not _rigid_done and _torn_weld_ok:
        for _pass in range(2):
            for t in tris:
                _cut = _cut_for(t)
                for a2, b2 in ((t[0], t[1]), (t[1], t[2]), (t[0], t[2])):
                    pa_, pb_ = vpart[a2], vpart[b2]
                    if pa_ != pb_ and frozenset((pa_, pb_)) not in _ADJ:
                        continue
                    db = sum((pos[a2][k] - pos[b2][k]) ** 2 for k in range(3)) ** 0.5
                    dw = sum((world[a2][k] - world[b2][k]) ** 2 for k in range(3)) ** 0.5
                    if dw <= _cut * max(db, 0.01) * s_perp or dw <= 0.06 * s_perp:
                        continue
                    mix = {}
                    for src_ in (vweights[a2], vweights[b2]):
                        for p_, w_ in src_.items():
                            mix[p_] = mix.get(p_, 0.0) + 0.5 * w_
                    tot = sum(mix.values()) or 1.0
                    nb = {p_: w_ / tot for p_, w_ in
                          sorted(mix.items(), key=lambda kv: -kv[1])[:4]}
                    vweights[a2] = dict(nb)
                    vweights[b2] = dict(nb)
                    mid = [(world[a2][k] + world[b2][k]) * 0.5 for k in range(3)]
                    world[a2] = tuple(world[a2][k] + 0.9 * (mid[k] - world[a2][k]) for k in range(3))
                    world[b2] = tuple(world[b2][k] + 0.9 * (mid[k] - world[b2][k]) for k in range(3))
                    _torn_welded += 1
                    _welded_verts.add(a2)
                    _welded_verts.add(b2)
    if _torn_welded:
        print(f"torn-edge weld: {_torn_welded} in-part edges closed instead of cut")
    sk_tris = []
    n_degen = 0
    _dbg_torn = []
    for t in tris:
        torn = False
        if _rigid_done:
            sk_tris.append(list(t)); continue
        if any(i in _welded_verts for i in t):
            sk_tris.append(list(t)); continue  # welded seams stay
        _cut = _cut_for(t)
        for a2, b2 in ((t[0], t[1]), (t[1], t[2]), (t[0], t[2])):
            db = sum((pos[a2][k] - pos[b2][k]) ** 2 for k in range(3)) ** 0.5
            dw = sum((world[a2][k] - world[b2][k]) ** 2 for k in range(3)) ** 0.5
            if dw > _cut * max(db, 0.01) * s_perp and dw > 0.06 * s_perp:
                torn = True
                break
        if torn:
            # profile tune "no_torn_cut": crush-class conforms (pikachu)
            # stretch tris BY DESIGN — the cut reads them as tears and
            # punches holes all over the mesh. Keep them instead.
            if TARGET_TUNE.get("no_torn_cut"):
                sk_tris.append(list(t))
                n_degen += 1
                continue
            n_degen += 1
            if os.environ.get("OSB_DEBUG"):
                _dbg_torn.append(t)
            continue
        sk_tris.append(list(t))
    if n_degen and TARGET_TUNE.get("no_torn_cut"):
        print(f"torn-tri cut suppressed (no_torn_cut): {n_degen} stretched "
              f"triangles KEPT")
    elif n_degen:
        print(f"torn-tri cut: {n_degen} triangles beyond 3x their part's "
              f"median stretch dropped")
        if _dbg_torn:
            import collections as _cl
            _ysd = [p[1] for p in pos]; _Hd = max(_ysd) - min(_ysd); _y0d = min(_ysd)
            hist = _cl.Counter()
            for t in _dbg_torn:
                parts_ = tuple(sorted({vpart[i] for i in t}))
                yb = round((sum(pos[i][1] for i in t)/3 - _y0d) / _Hd, 1)
                hist[(parts_, yb)] += 1
            for (parts_, yb), n in hist.most_common(12):
                print(f"  torn parts={parts_} y~{yb:.1f}H n={n}")
            # dump a few torso-internal torn triangles with bone weights
            shown = 0
            for t in _dbg_torn:
                if all(vpart[i] == 6 for i in t) and shown < 4:
                    shown += 1
                    print("  TORN TRI:")
                    for i in t:
                        bw = ", ".join(f"{names[jix[i][k]]}:{wts[i][k]:.2f}" for k in range(4) if wts[i][k] > 0)
                        print(f"    bind=({pos[i][0]:.3f},{pos[i][1]:.3f},{pos[i][2]:.3f}) world=({world[i][0]:.0f},{world[i][1]:.0f},{world[i][2]:.0f}) [{bw}]")
    # seam unify (general): UV-seam duplicate verts share a bind position
    # but are separate indices, and the per-EDGE weld passes above touch one
    # copy's edges without touching the other's — the copies drift apart in
    # weights/world, and any difference tears the texture seam open in
    # animated poses (slit-shaped holes in the coat/arms, worst on
    # stretched targets). Force position-coincident verts to share the
    # averaged weights and world position.
    if not _rigid_done:
        _pgroups = {}
        for _i in range(len(pos)):
            _pgroups.setdefault((round(pos[_i][0], 4), round(pos[_i][1], 4),
                                 round(pos[_i][2], 4)), []).append(_i)
        _unified = 0
        for _idxs in _pgroups.values():
            if len(_idxs) < 2:
                continue
            _mix = {}
            for _i in _idxs:
                for _p, _w in vweights[_i].items():
                    _mix[_p] = _mix.get(_p, 0.0) + _w
            _tot = sum(_mix.values()) or 1.0
            _top = dict(sorted(((_p, _w / _tot) for _p, _w in _mix.items()),
                               key=lambda kv: -kv[1])[:4])
            _t2 = sum(_top.values()) or 1.0
            _top = {_p: _w / _t2 for _p, _w in _top.items()}
            _wp = tuple(sum(world[_i][_k] for _i in _idxs) / len(_idxs) for _k in range(3))
            if any(vweights[_i] != _top or tuple(world[_i]) != _wp for _i in _idxs):
                _unified += 1
            for _i in _idxs:
                vweights[_i] = dict(_top)
                world[_i] = _wp
        if _unified:
            print(f"seam unify: {_unified} coincident-vertex groups share weights/position")
    # keep_vanilla replacement-drop: when a mapped joint keeps its VANILLA
    # geometry (Samus's cannon = her forearm+muzzle), the vanilla piece
    # REPLACES that limb segment — so clear the replacement out of the
    # kept bone's VOLUME (weight-based dropping missed sleeve fabric that
    # hangs over the forearm while weighted to the upper arm, leaving the
    # cannon hidden inside the sleeve with only the muzzle poking out).
    if TARGET_KEEP_VANILLA and TARGET_MAP is not None:
        _kept_canon = sorted({c for c, t in TARGET_MAP.items() if t in TARGET_KEEP_VANILLA})
        _capsules = []
        for _c in _kept_canon:
            _child = {8: 9, 9: 10, 14: 15, 15: 16, 19: 20, 20: 21,
                      24: 25, 25: 26}.get(_c)
            if _c in frames and _child in frames:
                _capsules.append((frames[_c][0], frames[_child][0]))
            elif _c in frames:
                # terminal part (hand): short capsule extending past the joint
                _o = frames[_c][0]
                _capsules.append((_o, [_o[0], _o[1] - 24, _o[2]]))
        _R = 34.0
        def _in_capsule(_pt):
            for _a, _b in _capsules:
                _ab = [_b[k] - _a[k] for k in range(3)]
                _len2 = sum(c * c for c in _ab) or 1e-9
                _t = sum((_pt[k] - _a[k]) * _ab[k] for k in range(3)) / _len2
                _t = max(-0.15, min(1.35, _t))
                _q = [_a[k] + _t * _ab[k] for k in range(3)]
                if sum((_pt[k] - _q[k]) ** 2 for k in range(3)) < _R * _R:
                    return True
            return False
        _vdrop = [_in_capsule(world[i]) for i in range(len(world))]
        _before = len(sk_tris)
        sk_tris = [t for t in sk_tris if not all(_vdrop[i] for i in t)]
        if _before != len(sk_tris):
            print(f"keep_vanilla: dropped {_before - len(sk_tris)} replacement tris "
                  f"inside vanilla-kept limb volume (parts {_kept_canon})")
    sk_verts = []
    for i in range(len(world)):
        n = rigid_n[i] if _rigid_done else vnormal(i)
        u, vv = uv[i]
        wl = [(p, w) for p, w in vweights[i].items()]
        sk_verts.append([round(world[i][0], 3), round(world[i][1], 3),
                         round(world[i][2], 3),
                         round(min(1.0, max(0.0, u)), 4),
                         round(min(1.0, max(0.0, vv)), 4),
                         round(n[0], 3), round(n[1], 3), round(n[2], 3),
                         wl])
    _emit = (lambda j: TARGET_MAP[j]) if TARGET_MAP is not None else (lambda j: j)
    if TARGET_MAP is not None:
        # merge influences that land on the same target joint (collapsed
        # chains: samus maps canonical forearm+hand both onto the cannon
        # joint 16) — duplicate entries would waste influence slots and a
        # {15:0.5, 16:0.5} vert is really a SOLID 1.0 on the target
        for v in sk_verts:
            _mw = {}
            for j, w in v[8]:
                tj = _emit(j)
                _mw[tj] = _mw.get(tj, 0.0) + w
            v[8] = sorted(_mw.items(), key=lambda kv: -kv[1])
    # ---- variant fit scale: the conform keeps the chibi silhouette
    # (mario-fitted head/gloves), which on tall small-headed target
    # skeletons (samus) tops out 20-30% above the vanilla fighter. The
    # mesh can't be shrunk here (verts ride the game skeleton), so emit
    # the ratio and let the game scale the fighter's root joint — the
    # same mechanism the CSS card scales use. 1.0 (omitted) when the
    # silhouette already fits.
    fit_scale = 1.0
    try:
        _fs_vp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              TARGET_PARTS_JSON or "vanilla-mario-parts.json")
        if os.path.exists(_fs_vp) and 12 in frames:
            _fs_parts = json.load(open(_fs_vp))
            if "12" in _fs_parts:
                _fo, _fR = frames[12]
                _v_top = max(_fo[1] + v[0]*_fR[0][1] + v[1]*_fR[1][1] + v[2]*_fR[2][1]
                             for v in _fs_parts["12"])
                _m_ys = [w[1] for w in world]
                _base = min(_m_ys)
                _m_top = max(_m_ys)
                if _m_top - _base > 1e-3:
                    fit_scale = (_v_top - _base) / (_m_top - _base)
                    fit_scale = max(0.75, min(1.0, fit_scale))
                    if fit_scale < 0.98:
                        print(f"fit scale: x{fit_scale:.3f} (mesh top {_m_top:.0f} vs vanilla {_v_top:.0f})")
                    else:
                        fit_scale = 1.0
    except (KeyError, IndexError, ValueError):
        fit_scale = 1.0

    skinned = {"fit_scale": round(fit_scale, 4),
               "joint_ids": sorted({_emit(j) for j in sk_joint_ids}),
               "verts": sk_verts,
               "tris": sk_tris,
               # the joint frames the world verts were authored against —
               # the game binds against THESE, not whatever pose the
               # fighter happens to be in when the mesh attaches
               "bind_frames": {str(_emit(j)): {"o": list(frames[j][0]),
                                               "R": [list(r) for r in frames[j][1]]}
                               for j in sk_joint_ids if j in frames},
               # joints whose vanilla geometry must be hidden: every target
               # joint the profile maps a canonical body joint onto (chain
               # joints like the neck often carry geometry on non-Mario
               # skeletons — Yoshi's joint 7 holds most of his head), plus
               # profile "blank_extra" for body joints outside the map
               # (Yoshi's hips at 5). Unmapped joints are accessories
               # (sword/shield/tie/tail/ears) and keep vanilla DLs +
               # modelpart behavior 1:1.
               # keep_vanilla: mapped joints whose VANILLA geometry should
               # render anyway (Samus's arm cannon: canonical hand maps
               # onto the cannon joint, but the cannon IS the fighter's
               # identity — keep it and let the replacement's hand ride
               # inside it).
               "blank_ids": sorted(({_emit(j) for j in sk_joint_ids}
                                    | (set(TARGET_MAP.values())
                                       if TARGET_MAP is not None else set())
                                    | set(TARGET_BLANK_EXTRA))
                                   - {0} - set(TARGET_KEEP_VANILLA))}

    # accessory snap: vanilla accessories (tail, sword, ...) attach at their
    # vanilla bind offset from the parent joint, which sits flush against
    # the VANILLA body. The replacement mesh has different proportions, so
    # profile "snap_accessories" roots get a parent-local delta that moves
    # the root onto the nearest replacement-mesh surface point (slightly
    # embedded so it reads as attached). The engine re-applies the delta
    # after animation each tick; child joints ride along.
    if TARGET_SNAP_ACCS:
        raw_frames = load_frames(frames_path)
        accs = []
        for aj in TARGET_SNAP_ACCS:
            if aj not in raw_frames:
                print(f"snap_accessories: joint {aj} missing frame, skipped")
                continue
            ro = raw_frames[aj][0]
            best_i, bd = None, 1e30
            for i, v in enumerate(sk_verts):
                d2 = (v[0]-ro[0])**2 + (v[1]-ro[1])**2 + (v[2]-ro[2])**2
                if d2 < bd:
                    bd, best_i = d2, i
            # pin the root to this VERTEX at runtime: the engine already
            # skins every vertex each tick, so the root follows the true
            # surface through any pose (anchoring to a single joint frame
            # drifts in crouches; a static parent-local delta is worse).
            # embed slightly along the inward normal so the accessory base
            # reads as attached without its geometry clipping far inside.
            accs.append({"joint": aj, "vert": best_i, "embed": 10.0})
            print(f"snap_accessories: joint {aj} pinned to vert {best_i} "
                  f"({math.sqrt(bd):.1f} world units away at bind), embed 10")
        if accs:
            skinned["accessories"] = accs

    if TARGET_MAP is not None:
        for p in out_parts:
            p["joint"] = TARGET_MAP.get(p["joint"], p["joint"])
    json.dump({"parts": out_parts, "atlas": atlas_path.rsplit("/", 1)[-1],
               "skinned": skinned},
              open(out_path, "w"))
    nv = sum(len(p["verts"]) for p in out_parts)
    nt = sum(len(p["tris"]) for p in out_parts)
    print(f"bundle v9 (rigged retarget): {len(out_parts)} parts, "
          f"{nv} verts, {nt} tris -> {out_path}")
    for p in out_parts:
        print(f"  joint {p['joint']:>2}: {len(p['verts']):5d} v {len(p['tris']):5d} t")


def pack_rgba16_dithered(atlas):
    """RGBA16 (5551, BE byte pairs) with ordered 4x4 Bayer dithering.

    Straight truncation to 5 bits posterizes the providers' soft baked
    shading into hard-edged contour patches (worst on dark cloth spanning
    only 2-3 levels — boyang's sleeve blotches), and in-game lighting
    slides those contours around as the mesh deforms. A +/-half-step
    ordered dither trades the contours for texel-level stipple that the
    RDP's bilinear filtering averages back into a smooth gradient."""
    import numpy as _npd
    a = _npd.asarray(atlas, _npd.float32)          # H x W x 4
    BAYER = (_npd.array([[0, 8, 2, 10], [12, 4, 14, 6],
                         [3, 11, 1, 9], [15, 7, 13, 5]],
                        _npd.float32) / 16.0 - 0.46875) * 8.0
    H, W = a.shape[:2]
    doff = _npd.tile(BAYER, (H // 4 + 1, W // 4 + 1))[:H, :W]
    doff = doff * float(os.environ.get("OSB_DITHER", "1"))
    # luminance gate: on near-black texels the +/-half-step stipple has
    # huge relative contrast (dark hair reads as crosshatch up close) and
    # dark regions are flat anyway, so fade the dither to zero below
    # V~48 and full strength above ~96.
    luma = a[..., :3].max(2)
    gate = _npd.clip((luma - 48.0) / 48.0, 0.0, 1.0)
    rgb = _npd.clip(a[..., :3] + (doff * gate)[..., None], 0, 255).astype(_npd.uint16) >> 3
    alpha = (a[..., 3] >= 128).astype(_npd.uint16)
    p16 = (rgb[..., 0] << 11) | (rgb[..., 1] << 6) | (rgb[..., 2] << 1) | alpha
    return p16.astype(">u2").tobytes()


def write_binary3(bundle_json_path, out_path):
    """OSB4: textured + lit bundle.

    Layout (all little-endian):
      'OSB4', u32 nparts, u32 texW, u32 texH,
      texW*texH u16 RGBA16 texels stored BIG-endian byte pairs (N64 order),
      per part: u32 joint, u32 nbatches,
        per batch: u32 nverts, u32 ntris,
          verts: s16 x,y,z,s,t (s/t in s10.5 texel units)
                 + s8 nx,ny,nz (unit normal * 127) + u8 pad,
          tris:  u8 a,b,c,pad.
    Triangles pre-batched to <=30 unique verts per gSPVertex window. The
    game renders these with G_LIGHTING enabled, inheriting the fighter's
    material light state (stage tint, damage color flashes).
    """
    d = json.load(open(bundle_json_path))
    base = bundle_json_path.rsplit("/", 1)[0]
    atlas = Image.open((base + "/" if base != bundle_json_path else "")
                       + d["atlas"]).convert("RGBA")
    TW, TH = atlas.size
    px = atlas.load()

    with open(out_path, "wb") as f:
        f.write(b"OSB4")
        f.write(struct.pack("<III", len(d["parts"]), TW, TH))
        f.write(pack_rgba16_dithered(atlas))

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
                    u, vv = v[6], v[7]
                    nx, ny, nz = (v[9:12] if len(v) >= 12 else [0.0, 1.0, 0.0])
                    s = max(0, min(TW*32 - 1, int(round(u * TW * 32))))
                    t = max(0, min(TH*32 - 1, int(round(vv * TH * 32))))
                    f.write(struct.pack("<hhhhhbbbB", x, y, z, s, t,
                                        int(max(-127, min(127, nx * 127))),
                                        int(max(-127, min(127, ny * 127))),
                                        int(max(-127, min(127, nz * 127))), 0))
                for t3 in btris:
                    f.write(struct.pack("<BBBB", t3[0], t3[1], t3[2], 0))
        print(f"batches: {total_b}, atlas {TW}x{TH}")
    print("binary3:", out_path)




def write_binary5(bundle_json_path, out_path, canonical_profile=None, morph_lambda=None):
    """OSB5: single CPU-skinned mesh (true smooth skinning in game).

    Layout (little-endian):
      'OSB5', u32 njoints, u32 nverts, u32 ntris, u32 texW, u32 texH,
      njoints * u32 joint_ids                (mario joint indices used)
      texW*texH u16 RGBA16 (BE byte pairs)
      verts: nverts * { f32 x,y,z (spawn WORLD space), s16 s,t,
                        u8 j0,j1,j2,j3 (indices into joint_ids),
                        u8 w0,w1,w2,w3 (weights, sum 255),
                        s8 nx,ny,nz, u8 pad }
      tris:  ntris * u16 a,b,c  (+ padding u16)
    The game allocates a Vtx array, attaches ONE DL to joint 0 (TopN),
    and每 frame recomputes vertex positions:
      world = sum_k w_k * M_k(now) * M_k(spawn)^-1 * v_spawn_world
      local = M_top(now)^-1 * world
    """
    d = json.load(open(bundle_json_path))
    base = bundle_json_path.rsplit("/", 1)[0]
    atlas = Image.open((base + "/" if base != bundle_json_path else "")
                       + d["atlas"]).convert("RGBA")
    TW, TH = atlas.size
    px = atlas.load()
    sk = d["skinned"]
    joint_ids = sk["joint_ids"]

    # ---- canonical retarget: ship the MARIO bundle onto another fighter.
    # The mesh, weights, and BIND section stay canonical (mario); only the
    # joint_ids are remapped to the target skeleton, and a CAN1 section
    # tells the engine to rebuild VIRTUAL joint frames each tick: mario's
    # bone offsets driven by the target joints' rotation deltas from their
    # own bind. Geometry quality is inherited from the validated mario
    # build instead of re-earned per target.
    canon = None
    if canonical_profile is not None:
        prof = json.load(open(canonical_profile))
        cmap = {int(k): int(v) for k, v in prof["map"].items()}
        missing = [j for j in joint_ids if j not in cmap]
        if missing:
            raise SystemExit(f"canonical: profile lacks map for joints {missing}")
        # canonical parent per mario joint; -1 anchors to fighter joint 0
        CPAR = {6: -1, 12: 6, 8: 6, 9: 8, 10: 9, 14: 6, 15: 14, 16: 15,
                19: -1, 20: 19, 22: 20, 24: -1, 25: 24, 27: 25}
        slot = {j: k for k, j in enumerate(joint_ids)}
        parents = []
        for j in joint_ids:
            pj = CPAR.get(j, -1)
            parents.append(-1 if pj == -1 else slot[pj])
        bf = sk["bind_frames"]
        # ---- optional proportion morph: stretch the canonical (mario)
        # mesh onto the TARGET skeleton's bone lengths (lam=0 pure chibi,
        # lam=1 full target proportions). The skeleton is scaled FIRST —
        # joint positions dictate overall size, so the skin can't come out
        # undersized — then each vert re-emits from the new joints with
        # its bone-local coords stretched along the bone axis only
        # (length follows the skeleton, girth stays the mesh's own).
        lam = float(morph_lambda or 0.0)
        if lam > 0.0:
            skel_path = os.path.join(os.path.dirname(canonical_profile),
                                     prof["name"] + ".skel")
            T = {}
            for line in open(skel_path):
                mm = re.search(r"joint=(\d+) parent=(-?\d+) "
                               r"world=\(([-\d.]+),([-\d.]+),([-\d.]+)\)", line)
                if mm:
                    T[int(mm.group(1))] = [float(mm.group(2 + i)) for i in (1, 2, 3)]
            bfp = {j: list(bf[str(j)]["o"]) for j in joint_ids}
            # yaw-align the CANONICAL side to the target's bind about the
            # vertical axis (shoulder-to-shoulder line, XZ projection).
            # The chibi bundle stands at MARIO's bind yaw; targets stand
            # at their own (samus -33deg, link -83deg) — the canonical
            # mesh always rendered yawed vs the vanilla/ship fighter.
            # Rotating mesh + normals + bind frames to the target's yaw
            # makes the baked bind face like the target, so the runtime
            # rotation deltas render it at the target's true facing.
            if 8 in joint_ids and 14 in joint_ids:
                am = [bfp[14][0]-bfp[8][0], bfp[14][2]-bfp[8][2]]
                at = [T[cmap[14]][0]-T[cmap[8]][0], T[cmap[14]][2]-T[cmap[8]][2]]
                yaw = math.atan2(at[1], at[0]) - math.atan2(am[1], am[0])
                cy, sy = math.cos(yaw), math.sin(yaw)
                px, pz = bfp[6][0], bfp[6][2]   # pivot: chest column

                def yawp(p):
                    dx, dz = p[0]-px, p[2]-pz
                    return [px + cy*dx - sy*dz, p[1], pz + sy*dx + cy*dz]
                for j in joint_ids:
                    bfp[j] = yawp(bfp[j])
                    R = bf[str(j)]["R"]
                    # world-side yaw on the bind basis: jm' = Y*jm
                    # with R rows as basis (jm = R^T): R' = R * Y^T
                    bf[str(j)]["R"] = [
                        [cy*R[r_][0] - sy*R[r_][2], R[r_][1],
                         sy*R[r_][0] + cy*R[r_][2]] for r_ in range(3)]
                for v in sk["verts"]:
                    v[0], v[1], v[2] = yawp(v[:3])
                    nx, nz = v[5], v[7]
                    v[5], v[7] = cy*nx - sy*nz, sy*nx + cy*nz
                print(f"canonical yaw-aligned to target: {math.degrees(yaw):+.1f} deg")
            o6b = bfp[6]
            ymin0 = min(v[1] for v in sk["verts"])
            rootb = [o6b[0], ymin0, o6b[2]]
            t0g = T[0]

            def seglen(a):
                return math.sqrt(a[0]*a[0] + a[1]*a[1] + a[2]*a[2]) or 1e-6

            def sub(a, b):
                return [a[0]-b[0], a[1]-b[1], a[2]-b[2]]

            def norm(a):
                n = seglen(a)
                return [a[0]/n, a[1]/n, a[2]/n]

            def rot_between(a, b):
                # minimal rotation matrix taking unit vector a to unit b
                k = [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
                c = a[0]*b[0]+a[1]*b[1]+a[2]*b[2]
                s2 = k[0]*k[0]+k[1]*k[1]+k[2]*k[2]
                if s2 < 1e-12:
                    return [[1,0,0],[0,1,0],[0,0,1]] if c > 0 else [[-1,0,0],[0,-1,0],[0,0,1]]
                K = [[0,-k[2],k[1]],[k[2],0,-k[0]],[-k[1],k[0],0]]
                f = (1.0-c)/s2
                G = [[0.0]*3 for _ in range(3)]
                for r_ in range(3):
                    for c_ in range(3):
                        kk2 = sum(K[r_][m]*K[m][c_] for m in range(3))
                        G[r_][c_] = (1.0 if r_ == c_ else 0.0) + K[r_][c_] + f*kk2
                return G

            def rotv(G, v):
                return [G[i][0]*v[0]+G[i][1]*v[1]+G[i][2]*v[2] for i in range(3)]

            # per-bone scale AND direction: blend each segment's length and
            # its bind direction toward the target's. At lam=1 the baked
            # skeleton IS the target bind — the target's rotation deltas
            # then reproduce its posed joint positions exactly at our size
            # (the charge stance held the cannon at face height because
            # samus's deltas landed on the chibi's differently-hung bind
            # arm). Collapsed target chains keep length and direction.
            s, bdir, A = {}, {}, {}
            for j in joint_ids:
                pj = CPAR.get(j, -1)
                if pj == -1:
                    dm, dt = sub(bfp[j], rootb), sub(T[cmap[j]], t0g)
                else:
                    dm, dt = sub(bfp[j], bfp[pj]), sub(T[cmap[j]], T[cmap[pj]])
                um = norm(dm)
                if seglen(dt) < 1.0:
                    s[j], u = 1.0, um
                else:
                    s[j] = 1.0 + lam * (seglen(dt)/seglen(dm) - 1.0)
                    ut = norm(dt)
                    u = norm([(1.0-lam)*um[i] + lam*ut[i] for i in range(3)])
                bdir[j] = u
                A[j] = rot_between(um, u)
            no = {}

            def place(j):
                if j in no:
                    return no[j]
                pj = CPAR.get(j, -1)
                base = rootb if pj == -1 else place(pj)
                ref = rootb if pj == -1 else bfp[pj]
                L = s[j] * seglen(sub(bfp[j], ref))
                no[j] = [base[i] + L * bdir[j][i] for i in range(3)]
                return no[j]
            for j in joint_ids:
                place(j)
            # vert stretch per owning joint: its geometry spans the bone
            # toward its unique child; leaves (head/hands/feet) keep size
            kids = {}
            for j in joint_ids:
                pj = CPAR.get(j, -1)
                if pj != -1:
                    kids.setdefault(pj, []).append(j)
            # per-joint geometry transform: rotate the joint's verts by the
            # bone it spans (unique child's bone; leaves follow the bone
            # arriving at them), then stretch along that bone's NEW axis
            stretch, axis, G = {}, {}, {}
            for j in joint_ids:
                ks = kids.get(j, [])
                if len(ks) == 1:
                    stretch[j], axis[j], G[j] = s[ks[0]], bdir[ks[0]], A[ks[0]]
                elif CPAR.get(j, -1) == -1:
                    stretch[j], axis[j], G[j] = s[j], bdir[j], A[j]  # torso
                else:
                    # leaf (head/hands/feet): keep size, follow the
                    # arriving bone's re-aim
                    stretch[j], axis[j], G[j] = 1.0, bdir[j], A[j]
            for v in sk["verts"]:
                acc = [0.0, 0.0, 0.0]
                nacc = [0.0, 0.0, 0.0]
                tw = 0.0
                for (ji, w) in v[8]:
                    if w <= 0.0:
                        continue
                    Lr = rotv(G[ji], sub(v[:3], bfp[ji]))
                    a, st = axis[ji], stretch[ji]
                    d = Lr[0]*a[0] + Lr[1]*a[1] + Lr[2]*a[2]
                    nr = rotv(G[ji], v[5:8])
                    for i in range(3):
                        acc[i] += w * (no[ji][i] + Lr[i] + (st - 1.0) * d * a[i])
                        nacc[i] += w * nr[i]
                    tw += w
                if tw > 0.0:
                    nl = seglen(nacc)
                    for i in range(3):
                        v[i] = acc[i] / tw
                        v[5+i] = nacc[i] / nl
            for j in joint_ids:
                bf[str(j)]["o"] = no[j]
                # rotate the bind frame with the joint's geometry so the
                # runtime skinning (rd * cbind, bind_local from BIND) keeps
                # the mesh glued to the re-aimed bones under posed deltas.
                # R stores basis vectors as rows (jm = R^T): jm' = G*jm
                # => R' = R * G^T
                R = bf[str(j)]["R"]
                Gj = G[j]
                bf[str(j)]["R"] = [[sum(R[r_][m]*Gj[c_][m] for m in range(3))
                                    for c_ in range(3)] for r_ in range(3)]
            print(f"canonical morph lam={lam}: " +
                  " ".join(f"{j}:{s[j]:.2f}" for j in joint_ids))
        # root anchor: ground point under the chest (TopN sits at ground).
        # bind_frames are world-space from the capture run, where the
        # chest sat exactly at the spawn TopN x/z — so this IS the
        # canonical TopN column, grounded at the mesh's lowest vertex.
        o6 = bf[str(6)]["o"] if "6" in bf else [0.0, 0.0, 0.0]
        ymin = min(v[1] for v in sk["verts"])
        can_root = [o6[0], ymin, o6[2]]
        blank = sorted((set(cmap.values()) | set(prof.get("blank_extra", ())))
                       - {0} - set(prof.get("keep_vanilla", ())))
        canon = {"tids": [cmap[j] for j in joint_ids], "parents": parents,
                 "root": can_root, "blank": blank,
                 "name": prof.get("name", "?")}
    verts = sk["verts"]      # [x,y,z,u,v,nx,ny,nz, [(ji,w),...]]
    tris = sk["tris"]

    with open(out_path, "wb") as f:
        f.write(b"OSB5")
        f.write(struct.pack("<IIIII", len(joint_ids), len(verts), len(tris), TW, TH))
        for j in (canon["tids"] if canon else joint_ids):
            f.write(struct.pack("<I", j))
        f.write(pack_rgba16_dithered(atlas))
        jindex = {j: k for k, j in enumerate(joint_ids)}
        for v in verts:
            x, y, z, u, vv, nx, ny, nz, wlist = v
            s = max(0, min(TW*32 - 1, int(round(u * TW * 32))))
            t = max(0, min(TH*32 - 1, int(round(vv * TH * 32))))
            wl = sorted(wlist, key=lambda kv: -kv[1])[:4]
            tot = sum(w for _, w in wl) or 1.0
            ws = [int(round(w / tot * 255)) for _, w in wl]
            while len(wl) < 4:
                wl.append((joint_ids[0], 0.0)); ws.append(0)
            ws[0] += 255 - sum(ws)
            f.write(struct.pack("<fffhh", x, y, z, s, t))
            f.write(struct.pack("<BBBB", *(jindex[j] for j, _ in wl)))
            f.write(struct.pack("<BBBB", *ws))
            f.write(struct.pack("<bbbB",
                                int(max(-127, min(127, nx*127))),
                                int(max(-127, min(127, ny*127))),
                                int(max(-127, min(127, nz*127))), 0))
        for t3 in tris:
            f.write(struct.pack("<HHHH", t3[0], t3[1], t3[2], 0))
        bf = sk.get("bind_frames")
        if bf and all(str(j) in bf for j in joint_ids):
            f.write(b"BIND")
            for j in joint_ids:
                o = bf[str(j)]["o"]; R = bf[str(j)]["R"]
                f.write(struct.pack("<fff", *o))
                # game matrix has basis vectors as COLUMNS: jm = R^T
                for r in range(3):
                    f.write(struct.pack("<fff", R[0][r], R[1][r], R[2][r]))
            print("binary5: embedded bind skeleton (BIND section)")
        blank_ids = canon["blank"] if canon else sk.get("blank_ids", joint_ids)
        f.write(b"BLNK")
        f.write(struct.pack("<I", len(blank_ids)))
        for j in blank_ids:
            f.write(struct.pack("<I", j))
        if set(blank_ids) != set(joint_ids):
            print(f"binary5: blank list {sorted(blank_ids)} "
                  f"(+{sorted(set(blank_ids) - set(joint_ids))} beyond skinned set)")
        accs = sk.get("accessories", [])
        if accs:
            f.write(b"ACC2")
            f.write(struct.pack("<I", len(accs)))
            for a in accs:
                f.write(struct.pack("<IIf", a["joint"], a["vert"], a["embed"]))
            print(f"binary5: {len(accs)} accessory vertex pin(s) (ACC2 section)")
        if canon:
            f.write(b"CAN1")
            f.write(struct.pack("<fff", *canon["root"]))
            for pslot in canon["parents"]:
                f.write(struct.pack("<i", pslot))
            print(f"binary5: CANONICAL retarget -> {canon['name']} "
                  f"(target joints {canon['tids']}, CAN1 section)")
        fs = float(sk.get("fit_scale", 1.0) or 1.0)
        if canon:
            fs = 1.0
        if fs < 0.995:
            f.write(b"SCAL")
            f.write(struct.pack("<f", fs))
            print(f"binary5: fit scale x{fs:.3f} (SCAL section)")
    print(f"binary5 (CPU-skinned): {len(verts)} verts, {len(tris)} tris, "
          f"{len(joint_ids)} joints -> {out_path}")


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--binary":
        write_binary(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 4 and sys.argv[1] == "--binary3":
        write_binary3(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 4 and sys.argv[1] == "--binary5":
        write_binary5(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 5 and sys.argv[1] == "--binary5-canonical":
        # --binary5-canonical mario-bundle.json out.osb skels/<t>.profile.json [morph_lambda]
        write_binary5(sys.argv[2], sys.argv[3], canonical_profile=sys.argv[4],
                      morph_lambda=float(sys.argv[5]) if len(sys.argv) > 5 else None)
    else:
        main()
