#!/usr/bin/env python3
"""Auto-calibrate the morph facing yaw for one target fighter.

Bakes a reference character at a grid of yaw trims (on the profile's
axis), captures a few deterministic tour ticks in pose mode, scores each
trim's silhouette against the vanilla fighter's render at the same ticks
(centroid-aligned, height-normalized IoU), and reports the argmax.
--write stores the winning trim into the profile as morph_yaw_trim.

Usage: python3 eval/yaw_calibrate.py samus [--bundle play/ui/boyangniu/bundle.json]
       [--trims -45,-30,-15,0,15,30,45] [--lam 0.5] [--write]
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.dirname(HERE)
TICKS = [459, 605, 729, 812, 1116]


def fkind_of(profile):
    return json.load(open(profile))["fkind"]


def silhouette(png):
    a = np.asarray(Image.open(png).convert("RGB")).astype(int)
    # pose captures clear to near-white; the fighter is everything else
    return (a.sum(2) < 690)


def norm_mask(m, size=160):
    ys, xs = np.where(m)
    if len(ys) < 50:
        return None
    m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = m.shape
    s = (size - 4) / h
    im = Image.fromarray((m * 255).astype(np.uint8)).resize(
        (max(2, int(w * s)), size - 4), Image.NEAREST)
    out = np.zeros((size, size), bool)
    a = np.asarray(im) > 127
    x0 = (size - a.shape[1]) // 2
    if x0 < 0:
        a = a[:, -x0:-x0 + size]
        x0 = 0
    out[2:2 + a.shape[0], x0:x0 + a.shape[1]] = a
    return out


def iou(a, b):
    return (a & b).sum() / max(1, (a | b).sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--bundle", default="play/ui/boyangniu/bundle.json")
    ap.add_argument("--trims", default="-45,-30,-15,0,15,30,45")
    ap.add_argument("--lam", default="0.5")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    profile = os.path.join(PIPE, "skels", f"{a.target}.profile.json")
    fk = fkind_of(profile)
    trims = [int(t) for t in a.trims.split(",")]
    wd = a.workdir or os.path.join(PIPE, "eval", "yawcal", a.target)
    os.makedirs(wd, exist_ok=True)

    van = os.path.join(HERE, "cells", f"vanilla-fk{fk}-pose", "shots")
    if not os.path.exists(os.path.join(van, f"frame_{TICKS[-1]}.png")):
        print("capturing vanilla reference...")
        subprocess.run(["python3", os.path.join(HERE, "capture_clip.py"),
                        "vanilla", os.path.join(HERE, "cells", f"vanilla-fk{fk}-pose"),
                        "--fkind", str(fk), "--pose"], cwd=PIPE, check=True)

    def bake_and_capture(trim):
        osb = os.path.join(wd, f"trim{trim}.osb")
        env = dict(os.environ, MORPH_YAW_TRIM=str(trim))
        r = subprocess.run(["python3", "convert_rigged.py", "--binary5-canonical",
                            a.bundle, osb, profile, a.lam],
                           cwd=PIPE, env=env, capture_output=True, text=True)
        if r.returncode:
            return trim, None, r.stderr[-200:]
        shots = os.path.join(wd, f"shots{trim}")
        r = subprocess.run(["python3", "run_eval.py", shots, "--frames-list",
                            ",".join(map(str, TICKS)), "--fkind", str(fk),
                            "--bundle", osb, "--pose"],
                           cwd=PIPE, capture_output=True, text=True)
        if r.returncode:
            return trim, None, (r.stdout + r.stderr)[-200:]
        return trim, shots, None

    results = {}
    with cf.ThreadPoolExecutor(min(6, len(trims))) as ex:
        for trim, shots, err in ex.map(bake_and_capture, trims):
            if err:
                print(f"trim {trim:+d}: FAILED {err}")
                continue
            score, n = 0.0, 0
            for t in TICKS:
                mp = os.path.join(shots, f"frame_{t}.png")
                vp = os.path.join(van, f"frame_{t}.png")
                if not (os.path.exists(mp) and os.path.exists(vp)):
                    continue
                mm = norm_mask(silhouette(mp))
                vm = norm_mask(silhouette(vp))
                if mm is None or vm is None:
                    continue
                score += iou(mm, vm)
                n += 1
            if n:
                results[trim] = score / n
                print(f"trim {trim:+d}: IoU {results[trim]:.4f} ({n} ticks)")
    if not results:
        sys.exit("no results")
    best = max(results, key=results.get)
    print(f"\nbest trim: {best:+d} deg (IoU {results[best]:.4f})")
    if a.write:
        p = json.load(open(profile))
        p["morph_yaw_trim"] = best
        json.dump(p, open(profile, "w"), indent=1)
        print(f"wrote morph_yaw_trim={best} to {profile}")


if __name__ == "__main__":
    main()
