#!/usr/bin/env python3
"""Re-roll characters whose mesh the sweep judged broken: fresh description under
the new material/cloth rules (+ roster category), fresh t-pose, fresh Tripo mesh,
reconvert through the facing gate; portrait/stock/emblem/voice are kept.
Then re-run the mesh check on the new bundle. Extra slugs may be given as args.
-> artifacts/batch-1000/reroll_broken.log ; backups in artifacts/batch-1000/reroll-backup/<slug>/"""
import json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
ROOT = "/Users/tdimson/projects/opensmash/pipeline"; os.chdir(ROOT)
sys.path.insert(0, "artifacts/batch-1000"); sys.path.insert(0, "pipeline")
import mesh_check
SKIP = {"theheadlesshorse", "humptydumpty"}   # judged 'broken' for being the shape they are
rows = [json.loads(l) for l in open("artifacts/batch-1000/mesh-sweep.jsonl")]
todo = sorted(({r["slug"] for r in rows if r["verdict"] == "broken"} - SKIP) | set(sys.argv[1:]))
slug = lambda n: re.sub(r"[^a-z0-9]", "", n.lower())[:16]
names = {}
for l in open("config/seed-roster/seed-roster-sa.txt"):
    if l.strip() and not l.startswith("#"):
        n, _, notes = l.rstrip("\n").partition("\t"); names[slug(n)] = (n, notes)
TARGETS = "captain fox kirby link luigi ness pikachu purin samus donkey yoshi".split()
def reroll(s):
    name, notes = names.get(s, (json.load(open(f"play/ui/{s}/character.json")).get("display", s), ""))
    bk = f"artifacts/batch-1000/reroll-backup/{s}"; os.makedirs(bk, exist_ok=True)
    for f in ("tpose.png", "character.json", "rigged.glb"):
        if os.path.exists(f"play/ui/{s}/{f}"): os.replace(f"play/ui/{s}/{f}", f"{bk}/{f}")
    for f in ("rigged.glb.part", "tripo_tasks.json", "bundle.json", "bundle-atlas.png", "facing_flipped"):
        if os.path.exists(f"play/ui/{s}/{f}"): os.remove(f"play/ui/{s}/{f}")
    for f in [f"play/{s}.osb", f"play/{s}.osb6"] + [f"play/{s}-{t}.osb" for t in TARGETS]:
        if os.path.exists(f): os.remove(f)
    cmd = [sys.executable, "pipeline/run_character.py", name, "--force-stage", "expand"] + (["--notes", notes] if notes else [])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=2400)
    if r.returncode != 0 or not os.path.exists(f"play/{s}.osb6"):
        return s, "FAILED " + (r.stdout + r.stderr)[-160:].replace("\n", " ")
    png = f"/tmp/reroll-{s}.png"
    subprocess.run([sys.executable, "pipeline/preview_bundle.py", f"play/ui/{s}/bundle.json", "skels/mario-frames.skel", png, "--yaw", "0", "--size", "300"], capture_output=True)
    try: v = mesh_check.check(f"play/ui/{s}/tpose.png", png); verdict = f"{v['verdict']} ({v.get('issue','')[:60]})"
    except Exception as e: verdict = "check error"
    return s, "ok -> " + verdict
print(f"{len(todo)} to re-roll: {todo}", flush=True)
with ThreadPoolExecutor(6) as ex:
    for s, msg in ex.map(reroll, todo):
        print(f"{time.strftime('%H:%M:%S')} {s}: {msg}", flush=True)
print("reroll done", flush=True)
