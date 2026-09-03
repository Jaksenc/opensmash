#!/usr/bin/env python3
"""Bake an in-engine Open Graph sprite for a fighter.

Boots the native BattleShip build straight into the VS matchup card
(scvsintro.c: CSS "selected" pose, fitted fovy-30 camera, the card's light rig)
with the fighter injected as P1, in SSB64_POSE_CAPTURE mode so only that
fighter is drawn. The frame is shot twice over two chroma clears
(SSB64_POSE_CAPTURE_FILL) and difference-matted into an RGBA cutout, then
fitted onto a 480x640 canvas like the studio's three.js preview so the OG
studio (web-prototype/src/OgStudio.jsx) can drop it in unchanged.

    python3 pipeline/og_sprite.py guyfieri --fkind 1
    python3 pipeline/og_sprite.py --api http://localhost:4181 guyfieri stevejobs

Output: play/ui/<slug>/og_sprite.png (override with --out for a single slug).
"""

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request

import numpy as np
from PIL import Image

PIPELINE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.environ.get("EVAL_BUILD", os.path.join(os.path.dirname(PIPELINE_ROOT), "BattleShip", "build-us"))
LOG = os.path.expanduser("~/Library/Application Support/BattleShip/ssb64.log")

# scvsintro.c slice geometry (320x240 design space): P1 is the first of two
# slices, <P1> <VS gap> <P2>.
VIEW_L, VIEW_R, VIEW_T, VIEW_B, VS_W = 10, 310, 10, 230, 50
P1_X0 = VIEW_L
P1_X1 = VIEW_L + (VIEW_R - VIEW_L - VS_W) // 2

OUT_W, OUT_H = 480, 640
FIT = 0.92           # fighter height as a fraction of the canvas (three.js used 1/1.08)
CHROMA = ("ff00ff", "00ff00")
# Results pose per body kind (SSB64_VSINTRO_WIN, scvsintro.c). The card's own
# "selected" poses bow the chibi Kirby (8) and Purin (10) bodies into the
# camera, which reads as a squashed head on a card; Kirby's Win2 is an upright
# face and Purin's Win1 tilts least. Other kinds keep the card default.
WIN_POSE = {8: "2", 9: "2", 10: "1"}
# Global frame to shoot. The card is held open (SSB64_VSINTRO_HOLD) so a
# results pose can settle: Luigi's Win1 is still mid-motion at 100 and
# identical from 130 on; nothing else changes between 100 and 130.
DEFAULT_FRAME = 130
# Kirby's Win2 faces the camera only around frames 100-120 (it turns away
# and settles backwards after 150), so that body shoots early.
FRAME_POSE = {8: 110}


def boot(fkind, bundle, fill, frames, shots, win=(0, 40)):
    """One native boot; returns {frame: (w, h, bgra bytes)}."""
    os.makedirs(shots, exist_ok=True)
    env = dict(os.environ)
    env.update({
        "SSB64_BOOT_BATTLE": f"{fkind},0,4,1",
        "SSB64_INJECT_BUNDLE": os.path.abspath(bundle),
        "SSB64_INJECT_FKIND": str(fkind),
        "SSB64_INJECT_PLAYER": "0",
        "SSB64_POSE_CAPTURE": "1",
        "SSB64_POSE_CAPTURE_FILL": fill,
        "SSB64_SCREENSHOT_FRAMES": ",".join(map(str, frames)),
        "SSB64_SCREENSHOT_DIR": shots,
        "SSB64_SCREENSHOT_RAW": "1",
        "SSB64_MAX_FRAMES": str(max(frames) + 4),
        "SSB64_MUTE": "1",
        "SSB64_VSINTRO_HOLD": "1",
    })
    if fkind in WIN_POSE and "SSB64_VSINTRO_WIN" not in os.environ:
        env["SSB64_VSINTRO_WIN"] = WIN_POSE[fkind]
    cfg_path = os.path.join(BUILD, "BattleShip.cfg.json")
    try:
        cfg = json.load(open(cfg_path))
        # Parallel boots each pin their own window position: macOS throttles
        # a fully occluded window, so tiles must at least partially show.
        cfg.setdefault("Window", {}).update({"Width": 1280, "Height": 960,
                                             "PositionX": int(win[0]),
                                             "PositionY": int(win[1]),
                                             "Fullscreen": {"Enabled": False}})
        json.dump(cfg, open(cfg_path, "w"), indent=1)
    except Exception as e:  # noqa: BLE001
        print("warn: could not pin window config:", e)
    subprocess.run(["./BattleShip"], cwd=BUILD, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    out = {}
    for name in os.listdir(shots):
        if not name.endswith(".raw"):
            continue
        digits = "".join(ch for ch in name if ch.isdigit())
        with open(os.path.join(shots, name), "rb") as f:
            w, h = struct.unpack("<II", f.read(8))
            out[int(digits)] = (w, h, f.read())
    return out


def to_rgb(raw):
    w, h, data = raw
    a = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 4)
    return a[:, :, [2, 1, 0]].astype(np.float32)  # BGRA -> RGB


def matte(img1, img2, bg1, bg2):
    """Difference matting over two known backgrounds -> (rgb float, alpha float)."""
    bg1 = np.array(bg1, np.float32)
    bg2 = np.array(bg2, np.float32)
    denom = np.abs(bg1 - bg2).sum()
    alpha = 1.0 - np.abs(img1 - img2).sum(axis=2) / denom
    alpha = np.clip(alpha, 0.0, 1.0)
    a3 = alpha[..., None]
    rgb = np.where(a3 > 0.02, (img1 - (1.0 - a3) * bg1) / np.maximum(a3, 1e-3), 0.0)
    return np.clip(rgb, 0, 255), alpha


def hex_rgb(s):
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def fit_sprite(rgb, alpha, w, h):
    """Crop to the P1 slice, then to the alpha bbox, and fit onto OUT_WxOUT_H."""
    # The window is pinned 4:3, but macOS shrinks a window that would hang
    # off the screen, so the capture can be any size: map the 320x240 design
    # space per axis and re-square the pixels below.
    sx, sy = w / 320.0, h / 240.0
    # inset 2 design px: the scissor edge leaves a column of the neighbouring
    # camera's clear (black VS gap) inside the slice bounds
    x0, x1 = int((P1_X0 + 2) * sx), int((P1_X1 - 2) * sx)
    y0, y1 = int((VIEW_T + 2) * sy), int((VIEW_B - 2) * sy)
    rgb, alpha = rgb[y0:y1, x0:x1], alpha[y0:y1, x0:x1]
    # kill chroma-clear speckle: anything under 1.5% alpha is background
    alpha = np.where(alpha < 0.015, 0.0, alpha)
    # scissor leaks: a neighbouring camera's clear can bleed a column/row of
    # black into the slice in BOTH passes (difference 0 -> alpha 1). A fighter
    # never spans the full slice height/width (the card pads its fit), so any
    # column or row that is opaque for >90% of its length is an edge artifact.
    solid = alpha > 0.5
    bad_cols = solid.mean(axis=0) > 0.9
    bad_rows = solid.mean(axis=1) > 0.9
    alpha[:, bad_cols] = 0.0
    alpha[bad_rows, :] = 0.0
    ys, xs = np.nonzero(alpha > 0.05)
    if len(ys) == 0:
        raise RuntimeError("no fighter pixels in the P1 slice")
    by0, by1, bx0, bx1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    rgba = np.dstack([rgb, alpha * 255.0]).astype(np.uint8)[by0:by1, bx0:bx1]
    sprite = Image.fromarray(rgba, "RGBA")
    bw, bh = sprite.size
    bh_square = bh * sx / sy  # height in the capture's horizontal pixel units
    scale = min(OUT_H * FIT / bh_square, OUT_W * FIT / bw)
    sprite = sprite.resize((max(1, round(bw * scale)), max(1, round(bh_square * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (OUT_W, OUT_H), (0, 0, 0, 0))
    canvas.paste(sprite, ((OUT_W - sprite.width) // 2, (OUT_H - sprite.height) // 2), sprite)
    return canvas, (bw, bh)


def bake(slug, fkind, frame, out_path, keep_dir=None, win=(0, 40)):
    bundle = os.path.join(PIPELINE_ROOT, "play", f"{slug}.osb6")
    if not os.path.isfile(bundle):
        raise FileNotFoundError(bundle)
    work = keep_dir or tempfile.mkdtemp(prefix=f"og-{slug}-")

    # The two chroma passes are independent boots: run them side by side.
    def one(index, fill):
        shots = os.path.join(work, fill)
        got = boot(fkind, bundle, fill, [frame], shots, (win[0] + index * 660, win[1]))
        if frame not in got:
            raise RuntimeError(f"{slug}: frame {frame} not captured (got {sorted(got)})")
        if keep_dir:
            Image.fromarray(to_rgb(got[frame]).astype(np.uint8)).save(os.path.join(work, f"raw-{fill}.png"))
        return got[frame]

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(one, index, fill) for index, fill in enumerate(CHROMA)]
        caps = [future.result() for future in futures]
    w, h = caps[0][0], caps[0][1]
    if (caps[1][0], caps[1][1]) != (w, h):
        raise RuntimeError(f"{slug}: chroma passes captured different sizes ({w}x{h} vs {caps[1][0]}x{caps[1][1]})")
    rgb, alpha = matte(to_rgb(caps[0]), to_rgb(caps[1]), hex_rgb(CHROMA[0]), hex_rgb(CHROMA[1]))
    canvas, bbox = fit_sprite(rgb, alpha, w, h)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    canvas.save(out_path, optimize=True)
    if not keep_dir:
        shutil.rmtree(work, ignore_errors=True)
    return bbox


def api_fkinds(api):
    with urllib.request.urlopen(f"{api.rstrip('/')}/api/characters") as r:
        d = json.load(r)
    chars = d["characters"] if isinstance(d, dict) else d
    return {c["slug"]: c["fkind"] for c in chars}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slugs", nargs="+")
    ap.add_argument("--fkind", type=int, default=None, help="base fighter kind (single slug); else from --api")
    ap.add_argument("--api", default="http://localhost:4181", help="dev server for slug -> fkind lookup")
    ap.add_argument("--frame", type=int, default=None, help="global frame to shoot (default per body kind; card is held open)")
    ap.add_argument("--out", default=None, help="output PNG (single slug)")
    ap.add_argument("--keep", default=None, help="keep raw captures in this dir (single slug)")
    ap.add_argument("--force", action="store_true", help="re-bake existing sprites")
    ap.add_argument("--win", default="0,40", help="window origin x,y for this job's game windows (parallel jobs tile)")
    a = ap.parse_args()
    if (a.out or a.keep or a.fkind is not None) and len(a.slugs) != 1:
        ap.error("--out/--keep/--fkind take exactly one slug")
    fkinds = {a.slugs[0]: a.fkind} if a.fkind is not None else api_fkinds(a.api)
    failed = []
    for slug in a.slugs:
        out = a.out or os.path.join(PIPELINE_ROOT, "play", "ui", slug, "og_sprite.png")
        if os.path.exists(out) and not a.force and not a.out:
            print(f"{slug}: exists, skip")
            continue
        if slug not in fkinds:
            print(f"{slug}: not in roster, skip")
            failed.append(slug)
            continue
        try:
            win = tuple(int(v) for v in a.win.split(","))
            frame = a.frame if a.frame is not None else FRAME_POSE.get(fkinds[slug], DEFAULT_FRAME)
            bbox = bake(slug, fkinds[slug], frame, out, a.keep, win)
            print(f"{slug}: fkind={fkinds[slug]} bbox={bbox[0]}x{bbox[1]} -> {os.path.relpath(out, PIPELINE_ROOT)}")
        except Exception as e:  # noqa: BLE001
            print(f"{slug}: FAILED {e}")
            failed.append(slug)
    if failed:
        print(f"{len(failed)} failed: {' '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
