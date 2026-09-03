#!/usr/bin/env python3
"""Re-record every roster announcer clip with the current generator settings.

Backs up each existing clip to batch-state/announcer-backup/<slug>.wav (kept if
already present), regenerates play/ui/<slug>/announcer.wav from character.json's
display name, and re-stages it into BattleShip/web-dist/bundles/<slug>.wav.
"""
import glob, json, os, shutil, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from pipeline.generate_announcer import generate_announcer
WEBDIST = os.path.join(HERE, "..", "BattleShip", "web-dist", "bundles")
BACKUP = os.path.join(HERE, "batch-state", "announcer-backup")
os.makedirs(BACKUP, exist_ok=True)
workers = int(sys.argv[1]) if len(sys.argv) > 1 else 8
only = set(sys.argv[2:])
# --skip-file <path>: slugs (one per line) already re-recorded by an earlier run
skip = set()
if "--skip-file" in sys.argv:
    i = sys.argv.index("--skip-file")
    skip = set(open(sys.argv[i + 1]).read().split())
    only = set(sys.argv[2:i]) | set(sys.argv[i + 2:])

def one(cdir):
    slug = os.path.basename(cdir)
    wav = os.path.join(cdir, "announcer.wav")
    display = json.load(open(os.path.join(cdir, "character.json"))).get("display", "").strip()
    if not display:
        return slug, "skip: no display"
    bak = os.path.join(BACKUP, slug + ".wav")
    if os.path.exists(wav) and not os.path.exists(bak):
        shutil.copyfile(wav, bak)
    for attempt in range(3):
        try:
            generate_announcer(display, wav)
            break
        except Exception as e:
            err = e; time.sleep(5 * (attempt + 1))
    else:
        return slug, f"FAIL: {err}"
    if os.path.isdir(WEBDIST):
        shutil.copyfile(wav, os.path.join(WEBDIST, slug + ".wav"))
    return slug, "ok"

dirs = [d for d in sorted(glob.glob(os.path.join(HERE, "play", "ui", "*")))
        if os.path.exists(os.path.join(d, "character.json")) and (not only or os.path.basename(d) in only)
        and os.path.basename(d) not in skip]
print(f"{len(dirs)} characters, {workers} workers", flush=True)
fails = 0
with ThreadPoolExecutor(workers) as ex:
    for i, fut in enumerate(as_completed(ex.submit(one, d) for d in dirs), 1):
        slug, st = fut.result()
        if st != "ok": fails += 1
        print(f"[{i}/{len(dirs)}] {slug}: {st}", flush=True)
print(f"done, {fails} failures", flush=True)
