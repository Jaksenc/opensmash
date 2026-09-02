#!/usr/bin/env python3
"""Run facing_check.py over every built character; one JSON line each -> batch-state/facing-sweep.jsonl"""
import json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
slugs = sorted(s for s in os.listdir("play/ui") if os.path.exists(f"play/ui/{s}/bundle.json") and os.path.exists(f"play/ui/{s}/tpose.png"))
skip = {"cthulhu", "thejerseydevil", "daftpunk"}
out = open("batch-state/facing-sweep.jsonl", "a")
def one(s):
    r = subprocess.run([sys.executable, "pipeline/facing_check.py", f"play/ui/{s}/bundle.json", f"play/ui/{s}/tpose.png"],
                       capture_output=True, text=True, timeout=600)
    try:
        d = json.loads(r.stdout.strip().splitlines()[-1]); d["slug"] = s
    except Exception:
        d = {"slug": s, "error": (r.stdout + r.stderr)[-200:]}
    return d
with ThreadPoolExecutor(8) as ex:
    for d in ex.map(one, [s for s in slugs if s not in skip]):
        out.write(json.dumps(d) + "\n"); out.flush()
        if d.get("flipped") or d.get("error"):
            print(time.strftime("%H:%M:%S"), d.get("slug"), "FLIPPED" if d.get("flipped") else "error", d.get("confidence", ""), flush=True)
print("sweep done", flush=True)
