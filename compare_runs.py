#!/usr/bin/env python3
"""Objective mismatch score between an injected eval run and the vanilla
reference run. Both runs replay identical inputs, so P2 and the stage are
pixel-identical — every differing pixel belongs to the injected P1 (vs the
vanilla P1 it replaced). Reports per-frame diff pixel count + mean color
distance inside the diff region, and writes overlay heatmaps.

Usage: compare_runs.py injected_dir vanilla_dir out_dir [--thresh 40]
"""
import os
import sys

import numpy as np
from PIL import Image


def main():
    inj_dir, van_dir, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    thresh = int(sys.argv[sys.argv.index("--thresh") + 1]) if "--thresh" in sys.argv else 40
    os.makedirs(out_dir, exist_ok=True)

    frames = sorted(f for f in os.listdir(inj_dir)
                    if f.startswith("frame_") and f.endswith(".png"))
    total = 0.0
    rows = []
    for fn in frames:
        vp = os.path.join(van_dir, fn)
        if not os.path.exists(vp):
            continue
        a = np.asarray(Image.open(os.path.join(inj_dir, fn)).convert("RGB"), dtype=np.int16)
        b = np.asarray(Image.open(vp).convert("RGB"), dtype=np.int16)
        if a.shape != b.shape:
            continue
        d = np.abs(a - b).sum(axis=2)
        mask = d > thresh
        npx = int(mask.sum())
        mean_d = float(d[mask].mean()) if npx else 0.0
        score = npx * mean_d / 1e6
        total += score
        rows.append((fn, npx, mean_d, score))

        ov = a.copy()
        ov[mask] = [255, 0, 255]
        Image.fromarray(ov.astype(np.uint8)).resize(
            (a.shape[1] // 4, a.shape[0] // 4)).save(os.path.join(out_dir, "ov_" + fn))

    print(f"{'frame':>16} {'diff_px':>9} {'mean_d':>7} {'score':>8}")
    for fn, npx, mean_d, score in rows:
        print(f"{fn:>16} {npx:>9} {mean_d:>7.1f} {score:>8.2f}")
    print(f"TOTAL score: {total:.2f}  (lower = closer to vanilla)")


if __name__ == "__main__":
    main()
