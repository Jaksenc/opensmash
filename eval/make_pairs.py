#!/usr/bin/env python3
"""Build the randomized pairwise comparison schedule.

Every config pair within each character whose clips exist becomes one
comparison. Pair order is shuffled with a fixed seed, and left/right
assignment is randomized per comparison, so neither position nor
adjacency leaks the technique. Writes eval/pairs.json.
"""
import itertools
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))


def main(seed=20260821):
    chars = json.load(open(os.path.join(HERE, "characters.json")))
    cfgs = json.load(open(os.path.join(HERE, "configs.json")))
    rng = random.Random(seed)
    pairs = []
    cells_dir = os.environ.get("EVAL_OUT", os.path.join(HERE, "cells"))
    out_path = os.environ.get("EVAL_PAIRS", os.path.join(HERE, "pairs.json"))
    whitelist = os.environ.get("EVAL_PAIR_WHITELIST")   # e.g. "A1:A2,B1:B2"
    wl = [tuple(x.split(":")) for x in whitelist.split(",")] if whitelist else None
    for ch in chars:
        arms = sorted({d.split("-", 1)[1] for d in os.listdir(cells_dir) if d.startswith(ch + "-")})
        avail = [cf for cf in arms if os.path.exists(os.path.join(cells_dir, f"{ch}-{cf}", "clip.mp4"))]
        combos = wl if wl else list(itertools.combinations(avail, 2))
        for a, b in combos:
            if a not in avail or b not in avail:
                continue
            left, right = (a, b) if rng.random() < 0.5 else (b, a)
            pairs.append({"id": f"{ch}:{a}:{b}", "char": ch, "display": chars[ch]["display"],
                          "left": left, "right": right})
    # seeded shuffle keyed on stable ids: re-running after more cells finish
    # adds pairs without changing existing ids (ratings stay valid)
    import hashlib
    pairs.sort(key=lambda q: hashlib.md5(f"{seed}:{q['id']}".encode()).hexdigest())
    json.dump(pairs, open(out_path, "w"), indent=1)
    print(f"{len(pairs)} comparisons across {len(chars)} characters")


if __name__ == "__main__":
    main()
