#!/usr/bin/env python3
"""Run the in-game mesh eval: deterministic replay + screenshots.

Boots BattleShip (Metal backend) straight into Mario-vs-Mario on Hyrule with
the scripted eval-tour replay, captures screenshots at the given frames,
downsizes them, and (optionally) injects an .osb bundle into P1.

Usage:
  run_eval.py out_dir [--bundle artifacts/experiments/plumber.osb] [--frames 380:1900:12]
              [--replay eval/fixtures/replays/eval-tour.rpl] [--dump] [--keep-full]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Override with EVAL_BUILD to A/B two builds against one replay (e.g. a
# pre-change binary vs the current one) without editing this file.
BUILD = os.environ.get(
    "EVAL_BUILD", "/Users/tdimson/projects/opensmash/BattleShip/build-us")
LOG = os.path.expanduser("~/Library/Application Support/BattleShip/ssb64.log")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--bundle", default=None, help=".osb to inject into P1")
    ap.add_argument("--frames", default="380:1900:12", help="start:stop:step")
    ap.add_argument("--frames-list", default=None, help="explicit comma list")
    ap.add_argument("--replay", default=os.path.join(
        ROOT, "eval", "fixtures", "replays", "eval-tour.rpl"))
    ap.add_argument("--fkind", type=int, default=0, help="fighter kind for BOTH players (self-mirror tour)")
    ap.add_argument("--pose", action="store_true", help="clean capture: draw only P1's fighter (no stage/HUD/P2)")
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
        "SSB64_BOOT_BATTLE": f"{args.fkind},{args.fkind},4,0",
        "SSB64_REPLAY_PLAY": os.path.abspath(args.replay),
        "SSB64_SCREENSHOT_FRAMES": frame_list,
        "SSB64_SCREENSHOT_DIR": shots,
        "SSB64_MAX_FRAMES": str(stop + 20),
        "SSB64_SCREENSHOT_RAW": "1",   # raw BGRA dumps; encoded below with ffmpeg
        "SSB64_MUTE": "1",             # eval boots run silent (10 parallel games)
    })
    if args.pose:
        env["SSB64_POSE_CAPTURE"] = "1"
    if args.bundle:
        env["SSB64_INJECT_BUNDLE"] = os.path.abspath(args.bundle)
        env["SSB64_INJECT_FKIND"] = str(args.fkind)
        env["SSB64_INJECT_PLAYER"] = "0"
    if args.dump:
        env["SSB64_DUMP_FRAMES"] = "2200"

    # pin the window so every capture has identical framing (the game
    # re-saves whatever size/position the OS gave it on each exit).
    # EVAL_WINX/EVAL_WINY let parallel workers (separate EVAL_BUILD clones)
    # tile their windows so none is fully occluded (macOS throttles
    # fully-hidden windows). Capture reads the Metal layer, so framing is
    # position-independent.
    cfg_path = os.path.join(BUILD, "BattleShip.cfg.json")
    try:
        cfg = json.load(open(cfg_path))
        cfg.setdefault("Window", {}).update({"Width": 1280, "Height": 960,
                                             "PositionX": int(os.environ.get("EVAL_WINX", 0)),
                                             "PositionY": int(os.environ.get("EVAL_WINY", 40)),
                                             "Fullscreen": {"Enabled": False}})
        json.dump(cfg, open(cfg_path, "w"), indent=1)
    except Exception as e:
        print("warn: could not pin window config:", e)
    # the log path is global (SDL pref dir), so under parallel workers it is
    # shared and racy — treat it as best-effort
    try:
        if os.path.exists(LOG):
            os.remove(LOG)
    except OSError:
        pass
    subprocess.run(["./BattleShip"], cwd=BUILD, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=True)
    try:
        shutil.copy(LOG, os.path.join(out, "run.log"))
    except OSError:
        open(os.path.join(out, "run.log"), "w").write("(log unavailable: parallel eval workers share one ssb64.log)\n")

    # raw -> png (full res into shots/, downscaled into out/) via ffmpeg,
    # in parallel; PNG encoding off the game's render thread.
    import struct
    from concurrent.futures import ThreadPoolExecutor

    def convert(name):
        rp = os.path.join(shots, name)
        with open(rp, "rb") as f:
            w, h = struct.unpack("<II", f.read(8))
        base = name[:-4]
        full = os.path.join(shots, base + ".png")
        small = os.path.join(out, base + ".png")
        sh = int(h * args.width / w) // 2 * 2
        common = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra",
                  "-s", f"{w}x{h}", "-i", "pipe:0"]
        with open(rp, "rb") as f:
            f.seek(8)
            data = f.read()
        outs = ["-vf", f"scale={args.width}:{sh}:flags=lanczos", "-frames:v", "1", small]
        if args.keep_full:
            subprocess.run(common + ["-frames:v", "1", full], input=data, check=True)
        subprocess.run(common + outs, input=data, check=True)
        os.remove(rp)

    raws = sorted(n for n in os.listdir(shots) if n.endswith(".raw"))
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(convert, raws))
    n = len(raws)
    if not args.keep_full:
        shutil.rmtree(shots)

    # quick sanity: injection + replay lines from the log
    for line in open(os.path.join(out, "run.log"), errors="replace"):
        if "OSB" in line or "Replay:" in line or "BOOT_BATTLE" in line:
            print(line.rstrip())
    print(f"{n} screenshots -> {out}")


if __name__ == "__main__":
    main()
