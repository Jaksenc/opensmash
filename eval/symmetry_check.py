#!/usr/bin/env python3
"""Mirror-symmetry metric for a converted bundle's skinned mesh.

Poses the OSB5 skinned mesh with exactly mirrored T-pose frames
(preview_bundle.tpose_frames), mirrors it across the sagittal plane, and
reports nearest-neighbour distances — overall and for arm-dominated verts.
The source GLBs are symmetric, so this is a direct measure of asymmetry
introduced by conversion.

Usage: symmetry_check.py bundle.json [bundle2.json ...]
"""
import json
import os
import sys

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from preview_bundle import tpose_frames  # noqa: E402

ARM = (8, 9, 10, 14, 15, 16)
LEG = (19, 20, 22, 24, 25, 27)


def measure(path):
    s = json.load(open(path))["skinned"]
    fr = tpose_frames(s)
    mats = {}
    for j, bf in s["bind_frames"].items():
        j = int(j)
        fo, fR = fr[j]
        mats[j] = (np.array(bf["o"]), np.linalg.inv(np.array(bf["R"])) @ np.array(fR),
                   np.array(fo))
    posed, dom = [], []
    for v in s["verts"]:
        p = np.array(v[0:3])
        acc = np.zeros(3)
        tot = 0.0
        for j, w in v[8]:
            bo, M, fo = mats[j]
            acc += w * ((p - bo) @ M + fo)
            tot += w
        posed.append(acc / (tot or 1.0))
        dom.append(max(v[8], key=lambda jw: jw[1])[0])
    posed = np.array(posed)
    dom = np.array(dom)
    height = posed[:, 1].max() - posed[:, 1].min()
    mir = posed.copy()
    o6z = fr[6][0][2]
    mir[:, 2] = 2 * o6z - mir[:, 2]
    d, _ = cKDTree(posed).query(mir)
    res = {"height": height, "all": d.mean()}
    for name, js in (("arm", ARM), ("leg", LEG)):
        m = np.isin(dom, js)
        res[name] = d[m].mean() if m.any() else float("nan")
        res[name + "_p95"] = float(np.percentile(d[m], 95)) if m.any() else float("nan")
    return res


if __name__ == "__main__":
    for path in sys.argv[1:]:
        r = measure(path)
        print(f"{os.path.basename(path):40s} all {r['all']:6.2f}  "
              f"arm {r['arm']:6.2f} (p95 {r['arm_p95']:6.2f})  "
              f"leg {r['leg']:6.2f} (p95 {r['leg_p95']:6.2f})  "
              f"height {r['height']:.0f}")
