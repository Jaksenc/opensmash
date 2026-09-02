#!/usr/bin/env python3
"""Grade the DOM/SVG character-select tile against the game's extracted assets.

Reads raw RGBA tiles exported by charselect.html?grade=1 (window.exportTiles()
POSTs them to the scratch server dir) and scores palette, brightness
structure, and label styling against fire_bg.png / grid_mario.png.
"""
import glob, os, sys
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets", "charselect")
SCRATCH = sys.argv[1] if len(sys.argv) > 1 else "."

def load_raw(prefix):
    files = sorted(glob.glob(os.path.join(SCRATCH, f"{prefix}_*.raw")), key=os.path.getmtime)
    f = files[-1]
    w, h = map(int, os.path.basename(f).rsplit("_", 1)[1].replace(".raw", "").split("x"))
    return np.frombuffer(open(f, "rb").read(), np.uint8).reshape(h, w, 4).astype(np.float32)

def composite(img, bg=(10, 2, 1)):
    a = img[..., 3:4] / 255.0
    return img[..., :3] * a + np.array(bg, np.float32) * (1 - a)

def grade_fire():
    ours = composite(load_raw("tile_fire"))
    ref = np.asarray(Image.open(os.path.join(ASSETS, "fire_bg.png")).convert("RGB"), np.float32)
    # the tile's top lip and bottom rule sit under the grid lattice on the
    # real screen, so grade only the band the player actually sees
    ours, ref = ours[2:-1], ref[2:-1]
    if ours.shape != ref.shape:
        ours = np.asarray(Image.fromarray(ours.astype(np.uint8)).resize((ref.shape[1], ref.shape[0])), np.float32)
    dmean = np.abs(ours.mean(axis=(0, 1)) - ref.mean(axis=(0, 1)))
    lo, lr = ours.mean(axis=2), ref.mean(axis=2)
    ho, _ = np.histogram(lo, 32, (0, 255), density=True)
    hr, _ = np.histogram(lr, 32, (0, 255), density=True)
    hist_int = float(np.minimum(ho, hr).sum() / max(hr.sum(), 1e-9))
    vcorr = float(np.corrcoef(lo.mean(axis=1), lr.mean(axis=1))[0, 1])
    hcorr = float(np.corrcoef(lo.mean(axis=0), lr.mean(axis=0))[0, 1])
    # hue: dominant channel ratios in the bright zone
    bo = ours[lo > 60]; br = ref[lr > 60]
    hue_d = 0.0
    if bo.size and br.size:
        ro = bo.mean(axis=0); rr = br.mean(axis=0)
        hue_d = float(np.abs(ro / max(ro.sum(), 1) - rr / max(rr.sum(), 1)).sum()) * 100
    color_score = max(0, 100 - float(dmean.mean()) * 2.5)
    score = 0.3 * color_score + 30 * hist_int + 15 * max(0, vcorr) + 15 * max(0, hcorr) \
            + max(0, 10 - hue_d)
    print(f"[fire] meanΔRGB=({dmean[0]:.1f},{dmean[1]:.1f},{dmean[2]:.1f}) "
          f"histInt={hist_int:.2f} vCorr={vcorr:.2f} hCorr={hcorr:.2f} hueΔ={hue_d:.1f}"
          f" -> {score:.1f}/100")
    return score

# The I4 glyph sprites are white; in-game they're tinted with a tan prim
# color (sampled from actual gameplay footage of the select screen).
IN_GAME_TINT = np.array([203, 188, 156], np.float32)

def grade_label():
    ours = composite(load_raw("tile_label"))
    ref_lbl = np.asarray(Image.open(os.path.join(ASSETS, "grid_mario.png")).convert("RGBA"), np.float32)
    mask = ref_lbl[..., 3] > 128
    ref_c = ref_lbl[..., :3][mask].mean(axis=0) * (IN_GAME_TINT / 255.0)
    top = ours[1:11, 1:44]
    bright = top[top.mean(axis=2) > 110]
    our_c = bright.mean(axis=0) if bright.size else np.zeros(3)
    d = float(np.abs(ref_c - our_c).mean())
    # glyph height ratio: reference glyphs are ~9px of a 12px strip on a 43px tile
    print(f"[label] game text≈({ref_c[0]:.0f},{ref_c[1]:.0f},{ref_c[2]:.0f}) "
          f"ours≈({our_c[0]:.0f},{our_c[1]:.0f},{our_c[2]:.0f}) Δ={d:.1f} -> {max(0,100-d*2):.1f}/100")
    return max(0, 100 - d * 2)

s1 = grade_fire()
s2 = grade_label()
print(f"TOTAL fire={s1:.1f} label={s2:.1f}")
