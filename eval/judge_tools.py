#!/usr/bin/env python3
"""LLM-judge helpers.
  judge_tools.py prompt <batch_index> [--batch 10]  -> prints a prompt for one batch of pairs
  judge_tools.py ingest verdicts.json                -> appends {"id","choice","reason"} entries as rater 'judge'
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))

def prompt(bi, bs):
    pairs = json.load(open(os.path.join(HERE, "pairs.json")))
    batch = pairs[bi*bs:(bi+1)*bs]
    lines = ["You are an impartial visual QA judge for generated Super Smash Bros 64 fighters.",
             "For each comparison below, read BOTH sheet images (each sheet = 29 frames of the same replay;",
             "in every frame the TOP row is the generated fighter (left fighter) and the BOTTOM row is vanilla Mario",
             "as a reference for how a native fighter reads). Judge as a PLAYER would: likeness to the named character,",
             "Smash-64 proportions, intact geometry (no holes/stretching/shards), clean texture, consistent motion.",
             "Decide which of LEFT or RIGHT is the better fighter overall, or TIE if genuinely indistinguishable.",
             "Return ONLY a JSON list: [{\"id\": <id>, \"choice\": \"left\"|\"right\"|\"tie\", \"reason\": \"<one sentence>\"}, ...]", ""]
    for p in batch:
        L = os.path.join(HERE, "cells", f"{p['char']}-{p['left']}", "sheet.png")
        R = os.path.join(HERE, "cells", f"{p['char']}-{p['right']}", "sheet.png")
        lines.append(f"Comparison id={p['id']} character={p['display']}\n  LEFT sheet: {L}\n  RIGHT sheet: {R}")
    print("\n".join(lines))

def ingest(path):
    pairs = {p["id"]: p for p in json.load(open(os.path.join(HERE, "pairs.json")))}
    verdicts = json.load(open(path))
    with open(os.path.join(HERE, "ratings.jsonl"), "a") as f:
        for v in verdicts:
            p = pairs[v["id"]]
            f.write(json.dumps({"id": p["id"], "char": p["char"], "left": p["left"], "right": p["right"],
                                "choice": v["choice"], "reason": v.get("reason", ""), "rater": "judge", "t": time.time()}) + "\n")
    print(f"ingested {len(verdicts)} judge verdicts")

if __name__ == "__main__":
    if sys.argv[1] == "prompt":
        bs = int(sys.argv[sys.argv.index("--batch")+1]) if "--batch" in sys.argv else 10
        prompt(int(sys.argv[2]), bs)
    else:
        ingest(sys.argv[2])
