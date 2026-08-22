#!/usr/bin/env python3
"""Capture clips+sheets for every finished cell; polls for new bundles.
   python3 eval/capture_all.py [--once]"""
import os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); PIPE = os.path.dirname(HERE)
CELLS = os.path.join(HERE, "cells")
once = "--once" in sys.argv
idle = 0
while True:
    todo = [d for d in sorted(os.listdir(CELLS))
            if os.path.exists(os.path.join(CELLS, d, "bundle.osb")) and not os.path.exists(os.path.join(CELLS, d, "clip.mp4"))]
    vd = os.path.join(CELLS, "vanilla")
    if not os.path.exists(os.path.join(vd, "clip.mp4")):
        print(time.strftime("%H:%M:%S"), "capture vanilla", flush=True)
        subprocess.run(["python3", os.path.join(HERE, "capture_clip.py"), "vanilla", vd], cwd=PIPE, capture_output=True, text=True)
        continue
    if not todo:
        if once or idle > 90:  # ~45 min with nothing new -> exit
            break
        idle += 1; time.sleep(30); continue
    idle = 0
    d = todo[0]
    print(time.strftime("%H:%M:%S"), "capture", d, flush=True)
    r = subprocess.run(["python3", os.path.join(HERE, "capture_clip.py"),
                        os.path.join(CELLS, d, "bundle.osb"), os.path.join(CELLS, d)],
                       cwd=PIPE, capture_output=True, text=True)
    if r.returncode != 0:
        print("  FAILED", r.stdout[-200:], r.stderr[-300:], flush=True)
        open(os.path.join(CELLS, d, "capture.failed"), "w").write(r.stdout + r.stderr)
        # avoid hot loop on a persistent failure
        os.rename(os.path.join(CELLS, d, "bundle.osb"), os.path.join(CELLS, d, "bundle.osb.failed"))
print("capture_all: done")
