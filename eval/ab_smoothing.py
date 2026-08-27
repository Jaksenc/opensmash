#!/usr/bin/env python3
"""Smoothing A/B experiment: post-claim weight re-smoothing ON (sm, default
converter) vs OFF (ns, --no-postsmooth), 6 custom meshes x 4 target
skeletons (mario/samus/luigi/link), blind pairwise rating.

Self-contained under eval/smoothing/ so the tournament ratings in
eval/ratings.jsonl are untouched. Serve with:

  EVAL_OUT=eval/smoothing/cells EVAL_PAIRS=eval/smoothing/pairs.json \
  EVAL_RATINGS=eval/smoothing/ratings.jsonl \
  python3 eval/eval_server.py --rater tom

Stages (each cell skipped if its output exists — delete to redo):
convert (parallel x3) -> binary5 -> capture_clip --pose (5 parallel game
instances, each in its own EVAL_BUILD clone). --pose = SSB64_POSE_CAPTURE:
the engine draws ONLY P1's fighter (+ accessories) on a grey-cleared frame
— no stage, HUD, P2 or effects — the clean-render mode for judging mesh
quality (same mode pose_compare.py uses).
"""
import hashlib
import json
import os
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.dirname(HERE)
ROOT = os.path.join(HERE, "smoothing")
BUILD = os.path.join(ROOT, "build")
CELLS = os.path.join(ROOT, "cells")

CHARS = {
    "queen":  ("Queen Elizabeth II", os.path.join(HERE, "round3", "cells", "queen-BT", "rigged.glb")),
    "obama":  ("Barack Obama",       os.path.join(PIPE, "play", "ui", "barackobama", "rigged.glb")),
    "boyang": ("Boyang Niu",         os.path.join(PIPE, "play", "ui", "boyangniu", "rigged.glb")),
    "joey":   ("Joey Flynn",         os.path.join(PIPE, "play", "ui", "joeyflynn", "rigged.glb")),
    "moritz": ("Moritz Baier-Lentz", os.path.join(PIPE, "play", "ui", "moritzbaierlentz", "rigged.glb")),
    "rohan":  ("Rohan Sahai",        os.path.join(PIPE, "play", "ui", "rohansahai", "rigged.glb")),
}
TARGETS = {"mario": 0, "samus": 3, "luigi": 4, "link": 5}
VARIANTS = {"sm": [], "ns": ["--no-postsmooth"]}


def log(msg):
    print(msg, flush=True)


def convert_cell(char, target, variant):
    _, rigged = CHARS[char]
    tag = f"{char}_{target}-{variant}"
    bundle = os.path.join(BUILD, f"{tag}.json")
    osb = os.path.join(BUILD, f"{tag}.osb")
    if os.path.exists(osb):
        return tag, True
    cmd = ["python3", "convert_rigged.py", "--mild-color", "--flatten"] + VARIANTS[variant]
    if target == "mario":
        cmd += ["--no-profile", rigged, "mario-frames.skel", bundle]
    else:
        cmd += ["--target", os.path.join("skels", f"{target}.profile.json"),
                rigged, os.path.join("skels", f"{target}.skel"), bundle]
    r = subprocess.run(cmd, cwd=PIPE, capture_output=True, text=True, timeout=1800)
    open(os.path.join(BUILD, f"{tag}.convert.log"), "w").write(r.stdout + r.stderr)
    if r.returncode != 0:
        log(f"[{tag}] CONVERT FAILED: {r.stdout[-200:]}{r.stderr[-200:]}")
        return tag, False
    r = subprocess.run(["python3", "convert_rigged.py", "--binary5", bundle, osb],
                       cwd=PIPE, capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not os.path.exists(osb):
        log(f"[{tag}] BINARY5 FAILED: {r.stdout[-200:]}{r.stderr[-200:]}")
        return tag, False
    log(f"[{tag}] built")
    return tag, True


GAME_BUILD = os.path.join(PIPE, "..", "BattleShip", "build-us")


def make_build_clone(i):
    """Per-worker game dir: symlink everything, copy the cfg (game rewrites
    it on exit) — lets N game instances run without clobbering each other."""
    import shutil
    d = os.path.join(ROOT, f"buildworker{i}")
    if not os.path.exists(os.path.join(d, "BattleShip")):
        os.makedirs(d, exist_ok=True)
        src = os.path.abspath(GAME_BUILD)
        for name in os.listdir(src):
            dst = os.path.join(d, name)
            if os.path.lexists(dst):
                continue
            if name == "BattleShip.cfg.json":
                shutil.copy(os.path.join(src, name), dst)
            else:
                os.symlink(os.path.join(src, name), dst)
    return d


def capture_cell(char, target, variant, worker=0, attempts=3):
    """Crashed/failed runs are retried once: a lost attempt costs one game
    run, and the next attempt recaptures the cell from scratch. (The launch
    stagger this used to need is gone — the CAMetalLayer nextDrawable
    SIGSEGV was a drawable-texture over-release in libultraship, fixed
    2026-08-27; see BattleShip/docs/bugs/metal_drawable_texture_overrelease
    _2026-08-27.md.)"""
    tag = f"{char}_{target}-{variant}"
    osb = os.path.join(BUILD, f"{tag}.osb")
    cell = os.path.join(CELLS, f"{char}_{target}-{variant}")
    if os.path.exists(os.path.join(cell, "clip.mp4")):
        return True
    if not os.path.exists(osb):
        return False
    fk = TARGETS[target]
    env = dict(os.environ,
               EVAL_BUILD=make_build_clone(worker),
               EVAL_WINX=str(60 + 420 * worker))
    for att in range(attempts):
        r = subprocess.run(["python3", os.path.join(HERE, "capture_clip.py"), osb, cell,
                            "--fkind", str(fk), "--pose",
                            "--vanilla-dir", os.path.join(CELLS, f"vanilla-fk{fk}")],
                           cwd=PIPE, env=env, capture_output=True, text=True, timeout=3600)
        if r.returncode == 0 and os.path.exists(os.path.join(cell, "clip.mp4")):
            log(f"[{tag}] capture ok" + (f" (attempt {att + 1})" if att else ""))
            return True
        log(f"[{tag}] attempt {att + 1} failed: {(r.stdout + r.stderr)[-150:].strip()}")
    log(f"[{tag}] capture FAILED after {attempts} attempts")
    return False


def make_pairs(seed=20260827):
    rng = random.Random(seed)
    pairs = []
    for char, (display, _) in CHARS.items():
        for target in TARGETS:
            cellbase = f"{char}_{target}"
            if not all(os.path.exists(os.path.join(CELLS, f"{cellbase}-{v}", "clip.mp4"))
                       for v in ("sm", "ns")):
                continue
            left, right = ("sm", "ns") if rng.random() < 0.5 else ("ns", "sm")
            pairs.append({"id": f"{cellbase}:ns:sm", "char": cellbase,
                          "display": f"{display} · {target}",
                          "left": left, "right": right})
    pairs.sort(key=lambda q: hashlib.md5(f"{seed}:{q['id']}".encode()).hexdigest())
    json.dump(pairs, open(os.path.join(ROOT, "pairs.json"), "w"), indent=1)
    log(f"pairs.json: {len(pairs)} comparisons")


def main():
    os.makedirs(BUILD, exist_ok=True)
    os.makedirs(CELLS, exist_ok=True)
    jobs = [(c, t, v) for c in CHARS for t in TARGETS for v in VARIANTS]
    log(f"=== convert: {len(jobs)} cells (x3 parallel)")
    with ThreadPoolExecutor(max_workers=3) as ex:
        results = list(ex.map(lambda j: convert_cell(*j), jobs))
    built = {tag for tag, ok in results if ok}
    log(f"=== built {len(built)}/{len(jobs)}")
    # vanilla reference shots first (one per fkind, parallel) so the cell
    # captures never race to create them
    log("=== vanilla references (4 fkinds, parallel)")
    def _vanilla(i_fk):
        i, fk = i_fk
        vdir = os.path.join(CELLS, f"vanilla-fk{fk}")
        env = dict(os.environ, EVAL_BUILD=make_build_clone(i), EVAL_WINX=str(60 + 420 * i))
        for att in range(2):
            r = subprocess.run(["python3", os.path.join(HERE, "capture_clip.py"), "vanilla", vdir,
                                "--fkind", str(fk), "--pose",
                                "--vanilla-dir", vdir], cwd=PIPE, env=env,
                               capture_output=True, text=True, timeout=3600)
            if r.returncode == 0:
                log(f"[vanilla-fk{fk}] ok" + (f" (attempt {att + 1})" if att else ""))
                return
            log(f"[vanilla-fk{fk}] attempt {att + 1} failed: {(r.stdout + r.stderr)[-150:].strip()}")
        log(f"[vanilla-fk{fk}] FAILED after 2 attempts")
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(_vanilla, enumerate(sorted(set(TARGETS.values())))))
    log("=== capture: 5 parallel game instances (pose mode)")
    import queue as _q
    slots = _q.Queue()
    for i in range(5):
        slots.put(i)
    def _cap(j):
        c, t, v = j
        if f"{c}_{t}-{v}" not in built:
            return
        w = slots.get()
        try:
            capture_cell(c, t, v, worker=w)
        finally:
            slots.put(w)
    with ThreadPoolExecutor(max_workers=5) as ex:
        list(ex.map(_cap, jobs))
    make_pairs()
    log("=== DONE. Serve with:")
    log("EVAL_OUT=eval/smoothing/cells EVAL_PAIRS=eval/smoothing/pairs.json "
        "EVAL_RATINGS=eval/smoothing/ratings.jsonl python3 eval/eval_server.py")


if __name__ == "__main__":
    main()
