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
# Frames are keyed to the CURRENT make_replay.py tour (1863 ticks, incl.
# run-left/run-right): screenshot frame = replay input tick + 4, measured
# by correlating "screenshot frame N" log lines with the FRM dump stream
# (2026-08-27; an earlier "+40" note was wrong). Regenerate these from
# the .rpl.json marks whenever the TOUR changes.
CLIP_FRAMES = list(range(404, 1624, 3))
LABELS = {459: "walk",
          531: "run-left", 537: "run-left",
          594: "run", 605: "run", 616: "run",
          679: "walk-left", 729: "idle", 812: "jab", 852: "jab2",
          906: "ftilt", 976: "utilt", 1049: "crouch", 1064: "crouch",
          1116: "fsmash", 1126: "fsmash", 1196: "usmash", 1206: "usmash",
          1275: "jump", 1294: "air", 1344: "land", 1385: "jump2",
          1396: "nair", 1409: "air", 1459: "shield", 1479: "shield",
          1526: "taunt", 1539: "taunt", 1584: "idle",
          1664: "walk-back", 1724: "idle", 1806: "fireball", 1824: "fb-idle"}
SHEET_FRAMES = sorted(LABELS)
# fighter band as fractions of the frame (window size varies run to run)
BAND = (0.22, 0.05, 0.78, 0.75)


def crop_band(im):
    W, H = im.size
    return im.crop((int(W * BAND[0]), int(H * BAND[1]), int(W * BAND[2]), int(H * BAND[3])))


def capture(out_dir, bundle, frames, fkind=0, replay=None, pose=False):
    cmd = ["python3", "run_eval.py", out_dir, "--frames-list", ",".join(map(str, frames)),
           "--fkind", str(fkind)]
    if replay:
        cmd += ["--replay", replay]
    if bundle:
        cmd += ["--bundle", bundle]
    if pose:
        cmd += ["--pose"]
    r = subprocess.run(cmd, cwd=PIPE, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(r.stdout[-300:] + r.stderr[-300:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("out")
    ap.add_argument("--vanilla-dir", default=None)
    ap.add_argument("--fkind", type=int, default=0, help="fighter kind (both players)")
    ap.add_argument("--pose", action="store_true",
                    help="clean capture (SSB64_POSE_CAPTURE): draw ONLY P1's fighter "
                         "(+ its accessories) on a grey-cleared frame — no stage, HUD, "
                         "P2 or effects. Best for judging mesh quality.")
    a = ap.parse_args()
    if a.vanilla_dir is None:
        base = "vanilla" if a.fkind == 0 else f"vanilla-fk{a.fkind}"
        # pose refs live apart from full-scene refs: the shots are not
        # interchangeable and the existence check can't tell them apart
        a.vanilla_dir = os.path.join(HERE, "cells", base + ("-pose" if a.pose else ""))
    # per-fighter tour replay (fighter kinds are baked into the replay
    # metadata and must agree with BOOT_BATTLE)
    replay = os.path.join(PIPE, "eval-tour.rpl" if a.fkind == 0 else f"eval-tour-fk{a.fkind}.rpl")
    # ALWAYS regenerate: SHEET/CLIP frames above are keyed to the current
    # make_replay.py tour; a stale .rpl on disk would silently desync them.
    subprocess.run(["python3", "make_replay.py", replay,
                    "--p1", str(a.fkind), "--p2", str(a.fkind)], cwd=PIPE, check=True)
    os.makedirs(a.out, exist_ok=True)
    is_vanilla = a.bundle in ("vanilla", "none", "")
    frames = sorted(set(CLIP_FRAMES) | set(SHEET_FRAMES))
    shots = os.path.join(a.out, "shots")
    if not os.path.exists(os.path.join(shots, f"frame_{frames[-1]}.png")):
        shutil.rmtree(shots, ignore_errors=True)
        capture(shots, None if is_vanilla else os.path.abspath(a.bundle), frames, pose=a.pose,
                fkind=a.fkind, replay=replay)
    # a run can exit cleanly yet stop producing screenshots mid-way (the
    # Metal backend's nil-drawable skip under heavy parallel load) — fail
    # loudly instead of encoding a truncated clip that looks like success
    missing = [f for f in frames if not os.path.exists(os.path.join(shots, f"frame_{f}.png"))]
    if missing:
        shutil.rmtree(shots, ignore_errors=True)   # force a clean recapture on retry
        raise RuntimeError(f"capture incomplete: {len(missing)}/{len(frames)} frames "
                           f"missing (first {missing[0]}) — game stopped presenting?")

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
            capture(vshots, None, frames, fkind=a.fkind, replay=replay, pose=a.pose)
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
