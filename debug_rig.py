#!/usr/bin/env python3
"""Rig debug: render a rigged GLB textured with its skeleton overlaid, and
print bone-length / conform-scale diagnostics against the Mario skeleton.

Usage: debug_rig.py rigged.glb mario-frames.skel out.png
"""
import math
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from convert_glb import load_glb, read_accessor, load_frames
from convert_rigged import load_rigged, build_bone_map


def main():
    glb_path, frames_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    pos, nrm, uv, tris, img, jix, wts, names, jpos = load_rigged(glb_path)
    frames = load_frames(frames_path)

    # ---- numeric: meshy bone lengths vs mario bone lengths
    name_idx = {n: i for i, n in enumerate(names)}

    def mlen(a, b):
        pa, pb = jpos[name_idx[a]], jpos[name_idx[b]]
        return math.dist(pa, pb)

    def glen(a, b):
        return math.dist(frames[a][0], frames[b][0])

    posx = "Left" if jpos[name_idx["LeftArm"]][0] > jpos[name_idx["RightArm"]][0] else "Right"
    negx = "Right" if posx == "Left" else "Left"
    pairs = [
        ("torso", ("Hips", "neck"), (6, 11)),
        ("neck",  ("neck", "Head"), (11, 12)),
        (posx+" uparm", (posx+"Arm", posx+"ForeArm"), (8, 9)),
        (posx+" forearm", (posx+"ForeArm", posx+"Hand"), (9, 10)),
        (negx+" uparm", (negx+"Arm", negx+"ForeArm"), (14, 15)),
        (negx+" forearm", (negx+"ForeArm", negx+"Hand"), (15, 16)),
        (posx+" thigh", (posx+"UpLeg", posx+"Leg"), (19, 20)),
        (posx+" shin", (posx+"Leg", posx+"Foot"), (20, 21)),
        (negx+" thigh", (negx+"UpLeg", negx+"Leg"), (24, 25)),
        (negx+" shin", (negx+"Leg", negx+"Foot"), (25, 26)),
    ]
    print(f"{'bone':>14} {'mesh_len':>9} {'mario_len':>9} {'scale':>7}")
    scales = {}
    for label, (ma, mb), (ga, gb) in pairs:
        L1, L2 = mlen(ma, mb), glen(ga, gb)
        scales[label] = L2/max(L1, 1e-9)
        print(f"{label:>14} {L1:9.4f} {L2:9.2f} {scales[label]:7.1f}")

    # ---- rig acceptance gate: Meshy auto-rigging is stochastic and can
    # place joints asymmetrically or collapse a bone (seen: a left knee
    # 4cm from the ankle -> conform scale x1773 -> shredded leg). Reject
    # such rigs before conversion.
    fails = []
    for name in ("uparm", "forearm", "thigh", "shin"):
        l = scales.get(posx+" "+name) or scales.get("Left "+name)
        r = scales.get(negx+" "+name) or scales.get("Right "+name)
        if l and r and max(l, r)/min(l, r) > 1.35:
            fails.append(f"asymmetric {name}: L/R scale ratio {max(l,r)/min(l,r):.2f}")
    smax, smin = max(scales.values()), min(scales.values())
    if smax/smin > 3.0:
        fails.append(f"scale spread {smax/smin:.1f}x (max {smax:.0f} / min {smin:.0f})")
    if fails:
        print("RIG GATE: FAIL")
        for f in fails:
            print("  -", f)
    else:
        print("RIG GATE: PASS")

    # weight spread: how many parts hold >=0.12 / >=0.3 per vertex
    bone_map = build_bone_map(names, jpos)
    spread12 = spread30 = 0
    for ji, wt in zip(jix, wts):
        acc = {}
        for k in range(4):
            if wt[k] > 0:
                p = bone_map.get(names[ji[k]], (6,))[0]
                acc[p] = acc.get(p, 0) + wt[k]
        if sum(1 for w in acc.values() if w >= 0.12) > 1:
            spread12 += 1
        if sum(1 for w in acc.values() if w >= 0.3) > 1:
            spread30 += 1
    print(f"verts with >1 part @w>=0.12: {spread12}/{len(pos)}"
          f"   @w>=0.3: {spread30}/{len(pos)}")

    # ---- visual: textured front render + skeleton overlay
    import subprocess
    tmp = out_path + ".base.png"
    subprocess.run([sys.executable,
                    __file__.rsplit("/", 1)[0] + "/render_textured.py",
                    glb_path, tmp, "--size", "900", "--unlit"], check=True)
    im = Image.open(tmp)
    d = ImageDraw.Draw(im)
    W = H = 900
    ys = [v[1] for v in pos]
    ymin, ymax = min(ys), max(ys)
    sc = (H-80)/(ymax-ymin)

    def proj(p):
        return (W/2 + p[0]*sc, H-40-(p[1]-ymin)*sc)

    # parent links from gltf node hierarchy
    gltf, _ = load_glb(glb_path)
    skin = gltf["skins"][0]
    node_of = skin["joints"]
    parent = {}
    for ni, n in enumerate(gltf["nodes"]):
        for c in n.get("children", []):
            parent[c] = ni
    for k, node in enumerate(node_of):
        p = parent.get(node)
        a = proj(jpos[k])
        if p in node_of:
            b = proj(jpos[node_of.index(p)])
            d.line([a, b], fill=(80, 180, 255), width=3)
    for k, node in enumerate(node_of):
        a = proj(jpos[k])
        d.rectangle([a[0]-3, a[1]-3, a[0]+3, a[1]+3], fill=(255, 210, 74))
        d.text((a[0]+5, a[1]-10), names[k], fill=(255, 210, 74))
    im.save(out_path)
    print("overlay ->", out_path)


if __name__ == "__main__":
    main()
