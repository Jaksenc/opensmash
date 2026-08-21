#!/usr/bin/env python3
"""Run the in-game mesh eval: deterministic replay + screenshots.

Boots BattleShip (Metal backend) straight into Mario-vs-Mario on Hyrule with
the scripted eval-tour replay, captures screenshots at the given frames,
downsizes them, and (optionally) injects an .osb bundle into P1.

Usage:
  run_eval.py out_dir [--bundle plumber.osb] [--frames 380:1900:12]
              [--replay eval-tour.rpl] [--dump] [--keep-full]
"""
import argparse
import os
import shutil
import subprocess
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = "/Users/tdimson/projects/opensmash/BattleShip/build-us"
LOG = os.path.expanduser("~/Library/Application Support/BattleShip/ssb64.log")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--bundle", default=None, help=".osb to inject into P1")
    ap.add_argument("--frames", default="380:1900:12", help="start:stop:step")
    ap.add_argument("--frames-list", default=None, help="explicit comma list")
    ap.add_argument("--replay", default=os.path.join(ROOT, "eval-tour.rpl"))
    ap.add_argument("--dump", action="store_true", help="also dump FRM joint frames")
    ap.add_argument("--keep-full", action="store_true", help="keep full-res PNGs")
    ap.add_argument("--width", type=int, default=1504, help="downscale width")
    args = ap.parse_args()

    out = os.path.abspath(args.out_dir)
    shots = os.path.join(out, "shots-full")
    os.makedirs(shots, exist_ok=True)

    if args.frames_list:
        frame_list = args.frames_list
        stop = max(int(x) for x in frame_list.split(","))
    else:
        start, stop, step = (int(x) for x in args.frames.split(":"))
        frame_list = ",".join(str(i) for i in range(start, stop, step))

    env = dict(os.environ)
    env.update({
        "SSB64_BOOT_BATTLE": "0,0,4,0",
        "SSB64_REPLAY_PLAY": os.path.abspath(args.replay),
        "SSB64_SCREENSHOT_FRAMES": frame_list,
        "SSB64_SCREENSHOT_DIR": shots,
        "SSB64_MAX_FRAMES": str(stop + 20),
    })
    if args.bundle:
        env["SSB64_INJECT_BUNDLE"] = os.path.abspath(args.bundle)
        env["SSB64_INJECT_FKIND"] = "0"
        env["SSB64_INJECT_PLAYER"] = "0"
    if args.dump:
        env["SSB64_DUMP_FRAMES"] = "2200"

    if os.path.exists(LOG):
        os.remove(LOG)
    subprocess.run(["./BattleShip"], cwd=BUILD, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=True)
    shutil.copy(LOG, os.path.join(out, "run.log"))

    n = 0
    for name in sorted(os.listdir(shots)):
        if not name.endswith(".png"):
            continue
        img = Image.open(os.path.join(shots, name))
        h = int(img.height * args.width / img.width)
        img.resize((args.width, h), Image.LANCZOS).save(os.path.join(out, name))
        n += 1
    if not args.keep_full:
        shutil.rmtree(shots)

    # quick sanity: injection + replay lines from the log
    for line in open(os.path.join(out, "run.log"), errors="replace"):
        if "OSB" in line or "Replay:" in line or "BOOT_BATTLE" in line:
            print(line.rstrip())
    print(f"{n} screenshots -> {out}")


if __name__ == "__main__":
    main()
