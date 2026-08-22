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
    for ch in chars:
        avail = [cf for cf in cfgs if os.path.exists(os.path.join(HERE, "cells", f"{ch}-{cf}", "clip.mp4"))]
        for a, b in itertools.combinations(avail, 2):
            left, right = (a, b) if rng.random() < 0.5 else (b, a)
            pairs.append({"id": f"{ch}:{a}:{b}", "char": ch, "display": chars[ch]["display"],
                          "left": left, "right": right})
    # seeded shuffle keyed on stable ids: re-running after more cells finish
    # adds pairs without changing existing ids (ratings stay valid)
    import hashlib
    pairs.sort(key=lambda q: hashlib.md5(f"{seed}:{q['id']}".encode()).hexdigest())
    json.dump(pairs, open(os.path.join(HERE, "pairs.json"), "w"), indent=1)
    print(f"{len(pairs)} comparisons across {len(chars)} characters")


if __name__ == "__main__":
    main()
