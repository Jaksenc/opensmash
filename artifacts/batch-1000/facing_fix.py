#!/usr/bin/env python3
"""Reconvert every character the facing sweep flagged (or could not judge):
drop the base/variant .osb, .osb6 and bundle.json so run_character redoes the
convert stage, where the facing gate now re-runs convert_rigged with
--flip-facing when the render faces away. Deterministic, no model calls
except the $0.0004 gate. -> artifacts/batch-1000/facing_fix.log"""
import json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
rows = [json.loads(l) for l in open("artifacts/batch-1000/facing-sweep.jsonl")]
todo = sorted({r["slug"] for r in rows if r.get("flipped") or r.get("error")})
names = {}
for s in todo:
    names[s] = json.load(open(f"play/ui/{s}/character.json")).get("display", s)
TARGETS = "captain fox kirby link luigi ness pikachu purin samus donkey yoshi".split()
def fix(s):
    for f in (f"play/{s}.osb", f"play/{s}.osb6", f"play/ui/{s}/bundle.json", f"play/ui/{s}/bundle-atlas.png",
              f"play/ui/{s}/facing_flipped") + tuple(f"play/{s}-{t}.osb" for t in TARGETS):
        if os.path.exists(f): os.remove(f)
    # run_character's slug is derived from the NAME; character.json 'display' may differ
    # from the seed name, so pass the slug through a name that maps back to it
    name = next((l.strip() for l in open("config/seed-roster/seed-roster-sa.txt")
                 if l.strip() and __import__("re").sub(r"[^a-z0-9]", "", l.strip().lower())[:16] == s), None) or names[s]
    r = subprocess.run([sys.executable, "pipeline/run_character.py", name], capture_output=True, text=True, timeout=1800)
    flipped = "reconverting with --flip-facing" in r.stdout
    ok = r.returncode == 0 and os.path.exists(f"play/{s}.osb6")
    return s, ok, flipped, (r.stdout + r.stderr)[-200:].replace("\n", " ") if not ok else ""
print(f"{len(todo)} to reconvert", flush=True)
with ThreadPoolExecutor(6) as ex:
    for s, ok, flipped, err in ex.map(fix, todo):
        print(f"{time.strftime('%H:%M:%S')} {s}: {'ok' if ok else 'FAILED ' + err} {'(flipped)' if flipped else '(kept)'}", flush=True)
print("fix pass done", flush=True)
