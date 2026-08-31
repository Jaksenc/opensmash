#!/usr/bin/env python3
"""Parse a BattleShip run log (SSB64_DUMP_FRAMES output) into frames.json
for viewer.html.

Collects:
  FRMH: t=<tic> pl=<p> fk=<k> st=<s>          -- per-fighter frame header
  FRM:  t=<tic> pl=<p> j=<i> o=(..) x=(..) y=(..) z=(..)  -- joint world frame
  SKELDUMP: joint=<i> parent=<p> ...           -- rest-pose parent map

Output schema:
  { "parents": {j: parent},
    "frames": [ { "t": tic,
                  "players": { pl: { "fk": k, "st": s,
                                     "joints": { j: {"o":[..],"R":[[x],[y],[z]]} } } } } ] }

Usage: frames_from_log.py run.log frames.json
"""
import json
import re
import sys


def vec(s):
    return [float(v) for v in s.split(",")]


def main():
    log_path, out_path = sys.argv[1], sys.argv[2]

    pat_h = re.compile(r"FRMH: t=(\d+) pl=(\d+) fk=(-?\d+) st=(-?\d+)")
    pat_j = re.compile(
        r"FRM: t=(\d+) pl=(\d+) j=(\d+) o=\(([^)]+)\) x=\(([^)]+)\) y=\(([^)]+)\) z=\(([^)]+)\)")
    pat_p = re.compile(r"SKELDUMP: joint=(\d+) parent=(-?\d+)")

    parents = {}
    frames = {}  # tic -> {pl -> {...}}

    for line in open(log_path):
        m = pat_j.search(line)
        if m:
            t, pl, j = int(m.group(1)), int(m.group(2)), int(m.group(3))
            fr = frames.setdefault(t, {}).setdefault(pl, {"fk": 0, "st": 0, "joints": {}})
            fr["joints"][j] = {"o": vec(m.group(4)),
                               "R": [vec(m.group(5)), vec(m.group(6)), vec(m.group(7))]}
            continue
        m = pat_h.search(line)
        if m:
            t, pl = int(m.group(1)), int(m.group(2))
            fr = frames.setdefault(t, {}).setdefault(pl, {"fk": 0, "st": 0, "joints": {}})
            fr["fk"], fr["st"] = int(m.group(3)), int(m.group(4))
            continue
        m = pat_p.search(line)
        if m:
            parents[int(m.group(1))] = int(m.group(2))

    out = {"parents": parents,
           "frames": [{"t": t, "players": frames[t]} for t in sorted(frames)]}
    json.dump(out, open(out_path, "w"))
    n_j = sum(len(p["joints"]) for f in out["frames"] for p in f["players"].values())
    print(f"{len(out['frames'])} frames, {n_j} joint samples, "
          f"{len(parents)} parent entries -> {out_path}")


if __name__ == "__main__":
    main()
