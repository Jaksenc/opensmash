#!/usr/bin/env python3
"""Facing verification gate: render the converted payload from +x and -x
and run a frontal-face detector. Prints 'front', 'back' or 'unknown'.
   verify_facing.py bundle.json"""
import json, math, os, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from render_tpose import render

def main(bundle):
    import cv2
    b = json.load(open(bundle)); sk = b["skinned"]; verts = sk["verts"]
    P = np.array([v[:3] for v in verts], np.float32); UV = np.array([v[3:5] for v in verts], np.float32)
    N = np.array([v[5:8] for v in verts], np.float32); T = np.array(sk["tris"])
    atlas = np.asarray(Image.open(bundle.rsplit(".", 1)[0] + "-atlas.png").convert("RGB"), np.float32)
    cascs = [cv2.CascadeClassifier(cv2.data.haarcascades + n) for n in
             ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml")]
    def roty(a):
        c, s = math.cos(a), math.sin(a); return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], np.float32)
    score = {}
    for lab, ang in (("front", -math.pi / 2), ("back", math.pi / 2)):
        g = cv2.cvtColor(np.asarray(render(P, UV, T, N, atlas, roty(ang), 700)), cv2.COLOR_RGB2GRAY)
        score[lab] = sum(len(c.detectMultiScale(g, 1.08, 3, minSize=(50, 50))) for c in cascs)
    if score["front"] > 0 and score["back"] == 0: print("front")
    elif score["back"] > 0 and score["front"] == 0: print("back")
    else: print("unknown")
    print(json.dumps(score), file=sys.stderr)

if __name__ == "__main__":
    main(sys.argv[1])
