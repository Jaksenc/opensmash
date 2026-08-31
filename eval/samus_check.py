#!/usr/bin/env python3
"""Fast samus iteration loop: convert one character onto samus, print the
numeric scorecard, boot ONE game instance for four tour frames, and write
a cropped strip PNG for eyeball inspection. ~90s per iteration.

  pose_check: samus_check generalized via --target [--out strip.png] [--flags "--claim-freeze"]
  samus_check.py boyangniu --no-game        # numbers only, ~40s

Scorecard: arm aspect ratios at bind (mario-target parity = 0.36),
bone-coverage worst/arms/legs (stretch_eval, tour-only). The strip is
walk/run/jab/fsmash — the frames where thin arms and run gaps live.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.dirname(HERE)
SCRATCH = os.path.join(HERE, "samus_check")


def crop_fighter(im, pad=25):
    a = np.asarray(im.convert("RGB")).astype(int)
    mask = np.abs(a - a[8, 8]).sum(axis=2) > 40
    mask[:8, :] = mask[-8:, :] = False
    mask[:, :8] = mask[:, -8:] = False
    ys, xs = np.where(mask)
    if not len(xs):
        return im
    return im.crop((max(xs.min()-pad, 0), max(ys.min()-pad, 0),
                    min(xs.max()+pad, im.width), min(ys.max()+pad, im.height)))


def arm_aspect(bundle_path):
    smap = {int(k): int(v) for k, v in json.load(
        open(os.path.join(PIPE, "skels/samus.profile.json")))["map"].items()}
    b = json.load(open(bundle_path))["skinned"]
    F = {int(j): np.array(f["o"]) for j, f in b["bind_frames"].items()}
    out = {}
    for nm, a, bj in (("L-arm", 8, 9), ("R-arm", 14, 15)):
        ta, tb = smap[a], smap[bj]
        if ta not in F or tb not in F:
            continue
        oa, ob = F[ta], F[tb]
        ax = ob - oa
        L = np.linalg.norm(ax)
        if L < 1e-3:
            continue
        ax /= L
        pts = []
        for v in b["verts"]:
            w = sum(wt for j, wt in v[8] if j == ta)
            if w > 0.3:
                p = np.array(v[0:3]) - oa
                t = p @ ax
                if -0.2*L < t < 1.2*L:
                    pts.append(np.linalg.norm(p - t*ax))
        if pts:
            out[nm] = float(np.median(pts) / L)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("char", nargs="?", default="boyangniu")
    ap.add_argument("--out", default=None)
    ap.add_argument("--flags", default="", help="extra convert_rigged flags")
    ap.add_argument("--no-game", action="store_true")
    ap.add_argument("--tag", default="check", help="scratch file tag")
    args = ap.parse_args()

    os.makedirs(SCRATCH, exist_ok=True)
    bundle = os.path.join(SCRATCH, f"{args.char}-{args.tag}.json")
    osb = os.path.join(SCRATCH, f"{args.char}-{args.tag}.osb")
    out_png = args.out or os.path.join(SCRATCH, f"{args.char}-{args.tag}.png")

    converter = os.path.join(PIPE, "pipeline", "convert_rigged.py")
    evaluator = os.path.join(PIPE, "pipeline", "run_eval.py")
    cmd = ["python3", converter, "--mild-color", "--flatten",
           "--guidedflat"] + args.flags.split() + \
          ["--target", "skels/samus.profile.json",
           os.path.join("play/ui", args.char, "rigged.glb"),
           "skels/samus.skel", bundle]
    r = subprocess.run([c for c in cmd if c], cwd=PIPE,
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"convert failed:\n{r.stdout[-500:]}{r.stderr[-500:]}")
    for ln in r.stdout.splitlines():
        if "arm claim" in ln or "widen" in ln or "scale:" in ln:
            print(f"  {ln.strip()}")

    asp = arm_aspect(bundle)
    print("ARM ASPECT (bind, radius/len; mario parity 0.36): "
          + "  ".join(f"{k}={v:.2f}" for k, v in asp.items()))

    r = subprocess.run(["python3", "eval/stretch_eval.py", bundle,
                        "eval/streams/fk3.json", "--target", "samus",
                        "--min-t", "425", "--json", "/tmp/samus_check.json"],
                       cwd=PIPE, capture_output=True, text=True)
    d = json.load(open("/tmp/samus_check.json"))
    cov = {k: v[0] for k, v in d["cover"].items()}
    arms = sum(v for k, v in cov.items() if "arm" in k) / 4
    legs = sum(v for k, v in cov.items() if k[2:] in ("thigh", "shin")) / 4
    print(f"COVERAGE (tour): worst={max(cov.values()):.1f}%  "
          f"arms={arms:.1f}%  legs={legs:.1f}%   (good targets: ~1.4/0.6/1.1)")

    if args.no_game:
        return
    subprocess.run(["python3", converter, "--binary5", bundle, osb],
                   cwd=PIPE, check=True, capture_output=True)
    shots = os.path.join(SCRATCH, f"shots-{args.char}-{args.tag}")
    r = subprocess.run(["python3", evaluator, shots, "--bundle", osb,
                        "--fkind", "3", "--replay", "eval/fixtures/replays/eval-tour-fk3.rpl",
                        "--frames-list", "459,605,812,1116",
                        "--pose", "--width", "1280"],
                       cwd=PIPE, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"capture failed:\n{r.stdout[-300:]}{r.stderr[-300:]}")
    H = 380
    cells = []
    for f, lbl in ((459, "walk"), (605, "run"), (812, "jab"), (1116, "fsmash")):
        im = crop_fighter(Image.open(os.path.join(shots, f"frame_{f}.png")))
        cells.append((lbl, im.resize((int(im.width*H/im.height), H))))
    W = max(im.width for _, im in cells) + 12
    out = Image.new("RGB", (W*len(cells), H+28), (255, 255, 255))
    dr = ImageDraw.Draw(out)
    for i, (lbl, im) in enumerate(cells):
        dr.text((W*i+6, 6), f"{lbl}  [{args.char} {args.tag}]", fill=(0, 0, 0))
        out.paste(im, (W*i+(W-im.width)//2, 26))
    out.save(out_png)
    print(f"STRIP -> {out_png}")


if __name__ == "__main__":
    main()
