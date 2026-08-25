#!/usr/bin/env python3
"""Clean pose-capture comparison: reference (vanilla) vs test (bundle).

Runs the deterministic move tour twice in SSB64_POSE_CAPTURE mode — only
player 1's fighter renders, on a black frame with no stage, HUD, effects,
or opponent — then builds a web player that shows the two runs side by side,
frame-aligned: play as synced video, step frame by frame, or flicker-overlay
them on the same panel.

Usage:
  pose_compare.py bundle.osb out_dir --fkind 3 [--step 2]
Viewer lands at BattleShip/web-dist/eval/<out-name>/ (dev server route
/eval/<out-name>/).
"""
import argparse
import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.dirname(HERE)

TOUR_START = 360   # replay ticks (control unlocks at the GO, tick ~370)


def capture(out_dir, bundle, fkind, replay, frames):
    cmd = ["python3", "run_eval.py", out_dir, "--frames-list", ",".join(map(str, frames)),
           "--fkind", str(fkind), "--replay", replay, "--pose", "--width", "960"]
    if bundle:
        cmd += ["--bundle", bundle]
    r = subprocess.run(cmd, cwd=PIPE, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(r.stdout[-400:] + r.stderr[-400:])


def web_capture_single(a, name, replay, frames, shots, bundle_path=None):
    """Browser-based capture: stage inputs on the dev server, open the
    capture URL, and collect the uploaded frames from web-captures/."""
    import time
    bs = os.path.join(os.path.dirname(PIPE), "BattleShip")
    dist = os.path.join(bs, "web-dist")
    caps = os.path.join(bs, "web-captures")
    os.makedirs(os.path.join(dist, "replays"), exist_ok=True)
    shutil.copy(replay, os.path.join(dist, "replays", os.path.basename(replay)))
    shutil.rmtree(shots, ignore_errors=True)
    capdir = f"pose-{name}-{'test' if bundle_path else 'ref'}"
    shutil.rmtree(os.path.join(caps, capdir), ignore_errors=True)
    q = {
        "SSB64_BOOT_BATTLE": f"{a.fkind},{a.fkind},4,0",
        "SSB64_POSE_CAPTURE": "1",
        "replay": f"replays/{os.path.basename(replay)}",
        "capture": f"{frames[0]}:{frames[-1] + a.step}:{a.step}",
        "capname": capdir,
        "cb": str(int(time.time())),
    }
    if bundle_path:
        bname = os.path.basename(bundle_path)
        shutil.copy(bundle_path, os.path.join(dist, "bundles", bname))
        q["inject"] = f"bundles/{bname}"
        q["fkind"] = str(a.fkind)
        q["player"] = "0"
    url = "http://localhost:8600/index.html?" + "&".join(f"{k}={v}" for k, v in q.items())
    print(f"opening {url}")
    subprocess.run(["open", url], check=False)
    src = os.path.join(caps, capdir)
    want = len(frames)
    deadline = time.time() + 600
    have = 0
    while time.time() < deadline:
        have = len(os.listdir(src)) if os.path.isdir(src) else 0
        if have >= want:
            break
        time.sleep(3)
    else:
        raise RuntimeError(f"web capture timed out ({capdir}: "
                           f"{have}/{want} frames) — is the tab open?")
    os.makedirs(os.path.dirname(shots), exist_ok=True)
    shutil.move(src, shots)
    print(f"captured {want} frames -> {shots}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("out")
    ap.add_argument("--fkind", type=int, default=0)
    ap.add_argument("--step", type=int, default=2, help="capture every Nth tick")
    ap.add_argument("--web", action="store_true",
                    help="capture in the browser instead of the native app (APPROXIMATE: the canvas readback can lag the simulation by a few ticks; native capture is tick-exact)")
    a = ap.parse_args()

    name = os.path.basename(os.path.normpath(a.out))

    replay = os.path.join(PIPE, f"eval-tour-fk{a.fkind}.rpl")
    subprocess.run(["python3", "make_replay.py", replay,
                    "--p1", str(a.fkind), "--p2", str(a.fkind)], cwd=PIPE, check=True)
    import hashlib
    import json
    rhash = hashlib.md5(open(replay, "rb").read()).hexdigest()[:8]
    tour_total = json.load(open(replay + ".json"))["total"]
    frames = list(range(TOUR_START, tour_total, a.step))

    test_shots = os.path.join(a.out, "test")
    ref_shots = os.path.join(HERE, "cells", f"pose-vanilla-fk{a.fkind}-s{a.step}-{rhash}")
    for shots, bundle in ((ref_shots, None), (test_shots, os.path.abspath(a.bundle))):
        if not os.path.exists(os.path.join(shots, f"frame_{frames[-1]}.png")):
            if a.web:
                web_capture_single(a, name, replay, frames, shots, bundle)
            else:
                shutil.rmtree(shots, ignore_errors=True)
                os.makedirs(shots, exist_ok=True)
                capture(shots, bundle, a.fkind, replay, frames)

    viewer = os.path.join(os.path.dirname(PIPE), "BattleShip", "web-dist", "eval", name)
    subprocess.run(["python3", os.path.join(HERE, "make_viewer.py"), test_shots, ref_shots,
                    viewer, "--name", name, "--labels", replay + ".json"], check=True)
    print(f"side-by-side viewer -> http://localhost:8600/eval/{name}/")


if __name__ == "__main__":
    main()
