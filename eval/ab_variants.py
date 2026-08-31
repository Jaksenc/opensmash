#!/usr/bin/env python3
"""Generalized converter A/B experiment: any two convert_rigged.py flag
sets, blind pairwise rating. 6 custom meshes x 4 target skeletons
(mario/samus/luigi/link) per run.

  ab_variants.py --name guard --a gd= --b ug=--no-adjguard

builds everything under eval/<name>/ (build/, cells/, pairs.json,
ratings.jsonl) and prints the eval_server.py command to serve the blind
eval. Variant syntax: label=flags, flags space-separated (empty = default
converter). Stages (each cell skipped if its output exists — delete to
redo): convert (parallel x3) -> binary5 -> capture_clip --pose (5
parallel game instances, each in its own EVAL_BUILD clone). --pose =
SSB64_POSE_CAPTURE: the engine draws ONLY P1's fighter on a grey-cleared
frame — the clean-render mode for judging mesh quality.

Derived from ab_smoothing.py (the one-off this generalizes; kept for the
recorded smoothing ratings).
"""
import argparse
import hashlib
import json
import os
import random
import subprocess
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.dirname(HERE)

CHARS = {
    "queen":  ("Queen Elizabeth II", os.path.join(PIPE, "play", "ui", "queen", "rigged.glb")),
    "obama":  ("Barack Obama",       os.path.join(PIPE, "play", "ui", "barackobama", "rigged.glb")),
    "boyang": ("Boyang Niu",         os.path.join(PIPE, "play", "ui", "boyangniu", "rigged.glb")),
    "joey":   ("Joey Flynn",         os.path.join(PIPE, "play", "ui", "joeyflynn", "rigged.glb")),
    "moritz": ("Moritz Baier-Lentz", os.path.join(PIPE, "play", "ui", "moritzbaierlentz", "rigged.glb")),
    "rohan":  ("Rohan Sahai",        os.path.join(PIPE, "play", "ui", "rohansahai", "rigged.glb")),
}
# captain excluded from pair evals until make_replay gets speed-tuned run
# segments: Falcon outruns the fixed pose-capture camera from tour tick
# ~605, leaving both variants' clips empty (2026-08-29)
TARGETS = {"mario": 0, "samus": 3, "luigi": 4, "link": 5}

ROOT = BUILD = CELLS = None   # set in main() from --name
VARIANTS = {}                 # label -> [flags]


def log(msg):
    print(msg, flush=True)


def convert_cell(char, target, variant):
    _, rigged = CHARS[char]
    tag = f"{char}_{target}-{variant}"
    bundle = os.path.join(BUILD, f"{tag}.json")
    osb = os.path.join(BUILD, f"{tag}.osb")
    if os.path.exists(osb):
        return tag, True
    converter = os.path.join(PIPE, "pipeline", "convert_rigged.py")
    cmd = ["python3", converter, "--mild-color", "--flatten"] + VARIANTS[variant]
    if target == "mario":
        cmd += ["--no-profile", rigged, "skels/mario-frames.skel", bundle]
    else:
        cmd += ["--target", os.path.join("skels", f"{target}.profile.json"),
                rigged, os.path.join("skels", f"{target}.skel"), bundle]
    r = subprocess.run(cmd, cwd=PIPE, capture_output=True, text=True, timeout=1800)
    open(os.path.join(BUILD, f"{tag}.convert.log"), "w").write(r.stdout + r.stderr)
    if r.returncode != 0:
        log(f"[{tag}] CONVERT FAILED: {r.stdout[-200:]}{r.stderr[-200:]}")
        return tag, False
    r = subprocess.run(["python3", converter, "--binary5", bundle, osb],
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
    tag = f"{char}_{target}-{variant}"
    osb = os.path.join(BUILD, f"{tag}.osb")
    cell = os.path.join(CELLS, tag)
    if os.path.exists(os.path.join(cell, "clip.mp4")):
        return True
    if not os.path.exists(osb):
        return False
    fk = TARGETS[target]
    env = dict(os.environ,
               EVAL_BUILD=make_build_clone(worker),
               # tile two rows of 5 — a single row runs off-screen past 5
               # workers and macOS throttles occluded/off-screen windows
               EVAL_WINX=str(60 + 420 * (worker % 5)),
               EVAL_WINY=str(60 + 360 * (worker // 5)))
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


def make_pairs(seed):
    va, vb = list(VARIANTS)
    rng = random.Random(seed)
    pairs = []
    for char, (display, _) in CHARS.items():
        for target in TARGETS:
            cellbase = f"{char}_{target}"
            if not all(os.path.exists(os.path.join(CELLS, f"{cellbase}-{v}", "clip.mp4"))
                       for v in (va, vb)):
                continue
            left, right = (va, vb) if rng.random() < 0.5 else (vb, va)
            pairs.append({"id": f"{cellbase}:{va}:{vb}", "char": cellbase,
                          "display": f"{display} · {target}",
                          "left": left, "right": right})
    pairs.sort(key=lambda q: hashlib.md5(f"{seed}:{q['id']}".encode()).hexdigest())
    json.dump(pairs, open(os.path.join(ROOT, "pairs.json"), "w"), indent=1)
    log(f"pairs.json: {len(pairs)} comparisons")


def main():
    global ROOT, BUILD, CELLS, VARIANTS
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="experiment name -> eval/<name>/")
    ap.add_argument("--a", required=True, help="variant A as label=flags (flags may be empty)")
    ap.add_argument("--b", required=True, help="variant B as label=flags")
    ap.add_argument("--seed", type=int, default=20260827)
    ap.add_argument("--workers", type=int, default=10,
                    help="parallel game instances for the capture stage")
    a = ap.parse_args()
    for spec in (a.a, a.b):
        label, _, flags = spec.partition("=")
        VARIANTS[label] = flags.split() if flags else []
    ROOT = os.path.join(HERE, a.name)
    BUILD = os.path.join(ROOT, "build")
    CELLS = os.path.join(ROOT, "cells")
    os.makedirs(BUILD, exist_ok=True)
    os.makedirs(CELLS, exist_ok=True)

    jobs = [(c, t, v) for c in CHARS for t in TARGETS for v in VARIANTS]
    log(f"=== convert: {len(jobs)} cells (x3 parallel)")
    with ThreadPoolExecutor(max_workers=3) as ex:
        results = list(ex.map(lambda j: convert_cell(*j), jobs))
    built = {tag for tag, ok in results if ok}
    log(f"=== built {len(built)}/{len(jobs)}")

    log("=== vanilla references (4 fkinds, parallel)")
    def _vanilla(i_fk):
        i, fk = i_fk
        vdir = os.path.join(CELLS, f"vanilla-fk{fk}")
        if os.path.exists(os.path.join(vdir, "clip.mp4")):
            log(f"[vanilla-fk{fk}] exists")
            return
        env = dict(os.environ, EVAL_BUILD=make_build_clone(i),
                   EVAL_WINX=str(60 + 420 * (i % 5)),
                   EVAL_WINY=str(60 + 360 * (i // 5)))
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

    log(f"=== capture: {a.workers} parallel game instances (pose mode)")
    import queue as _q
    slots = _q.Queue()
    for i in range(a.workers):
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
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(_cap, jobs))
    make_pairs(a.seed)
    rel = os.path.join("eval", a.name)
    log("=== DONE. Serve with:")
    log(f"EVAL_OUT={rel}/cells EVAL_PAIRS={rel}/pairs.json "
        f"EVAL_RATINGS={rel}/ratings.jsonl python3 eval/eval_server.py")


if __name__ == "__main__":
    main()
