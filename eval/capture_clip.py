#!/usr/bin/env python3
"""Capture a hover-autoplay clip + a 29-frame sheet for one bundle.

Runs the deterministic replay tour with the bundle injected, grabs every
3rd tick over the move tour, crops the fighter band (both fighters: P1 =
pipeline, P2 = vanilla Mario, a built-in reference), and encodes an mp4.
Also builds the verifier-style 29-frame sheet stacked over the vanilla
reference capture.

Usage: capture_clip.py bundle.osb out_dir [--vanilla]   (vanilla = no bundle)
"""
import argparse
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.dirname(HERE)
CLIP_FRAMES = list(range(440, 1300, 3))
SHEET_FRAMES = [410, 455, 470, 515, 557, 605, 675, 745, 760, 785, 815, 895, 910, 975, 990,
                1045, 1085, 1099, 1130, 1155, 1180, 1225, 1250, 1300, 1350, 1420, 1470, 1505, 1540]
LABELS = {410: "walk", 455: "idle", 470: "idle", 515: "jab", 557: "jab2", 605: "ftilt", 675: "utilt",
          745: "crouch", 760: "crouch", 785: "fsmash", 815: "fsmash", 895: "usmash", 910: "usmash",
          975: "jump", 990: "air", 1045: "land", 1085: "jump2", 1099: "nair", 1130: "air", 1155: "shield",
          1180: "shield", 1225: "taunt", 1250: "taunt", 1300: "idle", 1350: "walk-back", 1420: "idle",
          1470: "idle", 1505: "fireball", 1540: "fb-idle"}
# fighter band as fractions of the frame (window size varies run to run)
BAND = (0.22, 0.05, 0.78, 0.75)


def crop_band(im):
    W, H = im.size
    return im.crop((int(W * BAND[0]), int(H * BAND[1]), int(W * BAND[2]), int(H * BAND[3])))


def capture(out_dir, bundle, frames, fkind=0, replay=None):
    cmd = ["python3", "run_eval.py", out_dir, "--frames-list", ",".join(map(str, frames)),
           "--fkind", str(fkind)]
    if replay:
        cmd += ["--replay", replay]
    if bundle:
        cmd += ["--bundle", bundle]
    r = subprocess.run(cmd, cwd=PIPE, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(r.stdout[-300:] + r.stderr[-300:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("out")
    ap.add_argument("--vanilla-dir", default=None)
    ap.add_argument("--fkind", type=int, default=0, help="fighter kind (both players)")
    a = ap.parse_args()
    if a.vanilla_dir is None:
        a.vanilla_dir = os.path.join(HERE, "cells",
                                     "vanilla" if a.fkind == 0 else f"vanilla-fk{a.fkind}")
    # per-fighter tour replay (fighter kinds are baked into the replay
    # metadata and must agree with BOOT_BATTLE)
    replay = os.path.join(PIPE, "eval-tour.rpl" if a.fkind == 0 else f"eval-tour-fk{a.fkind}.rpl")
    if not os.path.exists(replay):
        subprocess.run(["python3", "make_replay.py", replay,
                        "--p1", str(a.fkind), "--p2", str(a.fkind)], cwd=PIPE, check=True)
    os.makedirs(a.out, exist_ok=True)
    is_vanilla = a.bundle in ("vanilla", "none", "")
    frames = sorted(set(CLIP_FRAMES) | set(SHEET_FRAMES))
    shots = os.path.join(a.out, "shots")
    if not os.path.exists(os.path.join(shots, f"frame_{frames[-1]}.png")):
        shutil.rmtree(shots, ignore_errors=True)
        capture(shots, None if is_vanilla else os.path.abspath(a.bundle), frames,
                fkind=a.fkind, replay=replay)

    # clip: crop band, encode
    clipdir = os.path.join(a.out, "clipframes")
    os.makedirs(clipdir, exist_ok=True)
    size = None
    for i, f in enumerate(CLIP_FRAMES):
        p = os.path.join(shots, f"frame_{f}.png")
        if not os.path.exists(p):
            continue
        im = crop_band(Image.open(p).convert("RGB"))
        if size is None:
            w, h = im.size
            size = (w - w % 2, h - h % 2)
        im.resize(size, Image.LANCZOS).save(os.path.join(clipdir, f"{i:04d}.png"))
    mp4 = os.path.join(a.out, "clip.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "20",
                    "-i", os.path.join(clipdir, "%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "23", "-movflags", "+faststart", mp4], check=True)
    shutil.rmtree(clipdir, ignore_errors=True)

    # sheet: 29 frames, cell over vanilla (reference auto-captured per fighter)
    if not is_vanilla:
        vshots = os.path.join(a.vanilla_dir, "shots")
        if not os.path.exists(os.path.join(vshots, f"frame_{frames[-1]}.png")):
            os.makedirs(a.vanilla_dir, exist_ok=True)
            capture(vshots, None, frames, fkind=a.fkind, replay=replay)
        sheet_rows = []
        for f in SHEET_FRAMES:
            p = os.path.join(shots, f"frame_{f}.png")
            vp = os.path.join(vshots, f"frame_{f}.png")
            if not (os.path.exists(p) and os.path.exists(vp)):
                continue
            top = crop_band(Image.open(p).convert("RGB")).resize((800, 412), Image.LANCZOS)
            bot = crop_band(Image.open(vp).convert("RGB")).resize((800, 412), Image.LANCZOS)
            col = Image.new("RGB", (800, 850), (10, 10, 10))
            col.paste(top, (0, 14)); col.paste(bot, (0, 436))
            d = ImageDraw.Draw(col)
            d.text((4, 1), f"{f} {LABELS.get(f, '')} TOP: pipeline", fill=(255, 255, 0))
            d.text((4, 424), f"BOTTOM: vanilla fkind {a.fkind}", fill=(0, 255, 0))
            col.save(os.path.join(a.out, f"pair_{f:04d}.png"))
            sheet_rows.append(col)
        # contact sheet of all pairs (6 per row) for quick viewing
        if sheet_rows:
            cols = 6
            tw, th = 400, 425
            rows = (len(sheet_rows) + cols - 1) // cols
            sheet = Image.new("RGB", (cols * tw, rows * th), (0, 0, 0))
            for i, c in enumerate(sheet_rows):
                sheet.paste(c.resize((tw, th), Image.LANCZOS), ((i % cols) * tw, (i // cols) * th))
            sheet.save(os.path.join(a.out, "sheet.png"))
    # web A/B flipbook: same-tick frames from the two runs, served by the
    # dev server (web-dist/eval/ is preserved across repackages)
    if not is_vanilla:
        viewer = os.path.join(os.path.dirname(PIPE), "BattleShip", "web-dist", "eval",
                              os.path.basename(os.path.normpath(a.out)))
        subprocess.run(["python3", os.path.join(HERE, "make_viewer.py"), shots, vshots,
                        viewer, "--name", os.path.basename(os.path.normpath(a.out))], check=True)
        print(f"A/B viewer -> http://localhost:8600/eval/{os.path.basename(os.path.normpath(a.out))}/")
    print(f"clip -> {mp4}")


if __name__ == "__main__":
    main()
