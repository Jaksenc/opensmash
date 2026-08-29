#!/usr/bin/env python3
"""Autonomous pre-judgment of an ab_variants run: for every pair, build a
blinded two-row comparison sheet (rows shuffled per pair), grade it with
the codex CLI, and write prejudge.jsonl + sheets for Claude's own pass.
The human's eval_server ratings remain the final word — this is the
overnight triage so obvious wins/regressions are known by morning.

  judge_pairs.py eval/overnight [--codex-workers 3] [--skip-codex]
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES = [(459, "walk"), (605, "run"), (729, "idle"), (812, "jab"),
          (976, "utilt"), (1116, "fsmash"), (1275, "jump")]

CODEX_PROMPT = """Two rows of in-game poses of the SAME N64-style chibi fighter built
by two different mesh converters (row1 = top, row2 = bottom; same frames).
Judge overall mesh quality: holes, squiggly/flattened/shredded limbs,
detached pieces, head placement, coherent silhouette. Texture/color is
identical — judge GEOMETRY only.
Answer EXACTLY:
WINNER: TOP or BOTTOM or TIE
CONFIDENCE: <1-5>
ISSUES_TOP: <worst problems in the top row, or none>
ISSUES_BOTTOM: <worst problems in the bottom row, or none>"""


def crop_fighter(im, pad=15):
    a = np.asarray(im.convert("RGB")).astype(int)
    # sample the background at the top-RIGHT corner: the caption bar can
    # reach past (8,8) on some captures and inverts the whole mask
    mask = np.abs(a - a[8, -8]).sum(axis=2) > 40
    mask[:8, :] = mask[-8:, :] = False
    mask[:, :8] = mask[:, -8:] = False
    ys, xs = np.where(mask)
    if not len(xs):
        return im
    return im.crop((max(xs.min()-pad, 0), max(ys.min()-pad, 0),
                    min(xs.max()+pad, im.width), min(ys.max()+pad, im.height)))


def row_strip(cell_dir, H=300):
    ims = []
    for f, _ in FRAMES:
        p = os.path.join(cell_dir, f"pair_{f:04d}.png")
        if not os.path.exists(p):
            continue
        im = crop_fighter(Image.open(p).convert("RGB").crop((0, 18, 800, 425)))
        ims.append(im.resize((int(im.width*H/im.height), H)))
    return ims


def make_sheet(run_dir, pid, a, b, out_path):
    """Blinded sheet: shuffle which variant is the top row (seeded by id)."""
    flip = int(hashlib.sha1(pid.encode()).hexdigest(), 16) % 2 == 1
    top, bottom = (b, a) if flip else (a, b)
    rows = [row_strip(os.path.join(run_dir, "cells", top)),
            row_strip(os.path.join(run_dir, "cells", bottom))]
    if not rows[0] or not rows[1]:
        return None
    W = max(sum(im.width+8 for im in r) for r in rows)
    H = rows[0][0].height
    out = Image.new("RGB", (W, H*2+40), (255, 255, 255))
    dr = ImageDraw.Draw(out)
    for r, ims in enumerate(rows):
        x = 0
        dr.text((4, r*(H+18)+2), ["row1 (top)", "row2 (bottom)"][r], fill=(0, 0, 0))
        for im in ims:
            out.paste(im, (x, r*(H+18)+16))
            x += im.width + 8
    out.save(out_path)
    return {"top": top, "bottom": bottom, "flip": flip}


def parse_codex(txt):
    d = {}
    for ln in txt.splitlines():
        if ":" in ln:
            k, v = ln.split(":", 1)
            d[k.strip().upper()] = v.strip()
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--codex-workers", type=int, default=3)
    ap.add_argument("--skip-codex", action="store_true")
    a = ap.parse_args()
    pairs = json.load(open(os.path.join(a.run_dir, "pairs.json")))
    sheets_dir = os.path.join(a.run_dir, "prejudge-sheets")
    os.makedirs(sheets_dir, exist_ok=True)
    tasks = []
    for p in pairs:
        pid = p["id"]
        out_png = os.path.join(sheets_dir, pid.replace(":", "_") + ".png")
        cellA = p["char"] + "-" + p["id"].split(":")[1]
        cellB = p["char"] + "-" + p["id"].split(":")[2]
        meta = make_sheet(a.run_dir, pid, cellA, cellB, out_png)
        if meta:
            tasks.append((pid, out_png, meta))
            print(f"sheet {pid} (top={meta['top'].split('-')[-1]})")

    results = []
    if not a.skip_codex:
        def run_one(t):
            pid, png, meta = t
            out = tempfile.mktemp(suffix=".txt")
            try:
                subprocess.run(
                    ["codex", "exec", "-i", png, "-m", "gpt-5.6-sol",
                     "-c", 'model_reasoning_effort="high"',
                     "--sandbox", "read-only", "-o", out, CODEX_PROMPT],
                    capture_output=True, text=True, timeout=420)
                d = parse_codex(open(out).read()) if os.path.exists(out) else {}
            except Exception as e:
                d = {"WINNER": f"ERROR {e}"}
            finally:
                if os.path.exists(out):
                    os.unlink(out)
            w = d.get("WINNER", "?").upper()
            tech = meta["top"].split("-")[-1] if "TOP" in w else \
                meta["bottom"].split("-")[-1] if "BOTTOM" in w else "tie"
            rec = {"pair": pid, "codex_winner_row": w,
                   "codex_winner": tech,
                   "confidence": d.get("CONFIDENCE", "?"),
                   "issues_top": d.get("ISSUES_TOP", ""),
                   "issues_bottom": d.get("ISSUES_BOTTOM", ""),
                   "top_variant": meta["top"].split("-")[-1]}
            print(f"[codex] {pid}: {tech} (conf {rec['confidence']})")
            return rec
        with ThreadPoolExecutor(max_workers=a.codex_workers) as ex:
            results = list(ex.map(run_one, tasks))
        with open(os.path.join(a.run_dir, "prejudge.jsonl"), "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        from collections import Counter
        c = Counter(r["codex_winner"] for r in results)
        print("codex tally:", dict(c))


if __name__ == "__main__":
    main()
