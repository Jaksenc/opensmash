#!/usr/bin/env python3
"""Rank techniques from pairwise ratings (Bradley-Terry) and measure
human-vs-LLM-judge agreement.

  python3 eval/analyze.py [--rater tom] [--judge judge]

Reads eval/ratings.jsonl. A tie counts as half a win each way.
"""
import argparse
import collections
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load(rater):
    out = []
    for line in open(os.environ.get("EVAL_RATINGS", os.path.join(HERE, "ratings.jsonl"))):
        r = json.loads(line)
        if r.get("rater") == rater:
            out.append(r)
    # keep the latest rating per pair id
    latest = {}
    for r in out:
        latest[r["id"]] = r
    return list(latest.values())


def bradley_terry(recs, items):
    """Iterative MM (Hunter 2004). Returns strength per item, normalized."""
    wins = collections.defaultdict(float)
    games = collections.defaultdict(float)
    for r in recs:
        a, b = r["left"], r["right"]
        if r["choice"] == "left":
            wa, wb = 1.0, 0.0
        elif r["choice"] == "right":
            wa, wb = 0.0, 1.0
        else:
            wa = wb = 0.5
        wins[a] += wa; wins[b] += wb
        games[(a, b)] += 1; games[(b, a)] += 1
    p = {i: 1.0 for i in items}
    for _ in range(200):
        new = {}
        for i in items:
            den = 0.0
            for j in items:
                if i == j or games[(i, j)] == 0:
                    continue
                den += games[(i, j)] / (p[i] + p[j])
            new[i] = (wins[i] + 1e-6) / den if den > 0 else p[i]
        s = sum(new.values()) / len(new)
        p = {i: v / s for i, v in new.items()}
    return p, wins


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rater", default="tom")
    ap.add_argument("--judge", default="judge")
    a = ap.parse_args()
    cfgs = json.load(open(os.environ.get("EVAL_CONFIGS", os.path.join(HERE, "configs.json"))))
    chars = json.load(open(os.path.join(HERE, "characters.json")))
    recs = load(a.rater)
    if not recs:
        print("no ratings yet"); return
    items = sorted({r["left"] for r in recs} | {r["right"] for r in recs})
    p, wins = bradley_terry(recs, items)
    print(f"== {len(recs)} comparisons by {a.rater}")
    print("Overall technique ranking (Bradley-Terry strength; higher = preferred):")
    for i in sorted(items, key=lambda k: -p[k]):
        print(f"  {i}  {p[i]:5.2f}   wins {wins[i]:.1f}   {cfgs.get(i, {}).get('label', '')}")
    # head-to-head matrix
    print("\nHead-to-head win rate (row beats column):")
    hh = collections.defaultdict(lambda: [0.0, 0])
    for r in recs:
        l, rr = r["left"], r["right"]
        s = {"left": (1, 0), "right": (0, 1), "tie": (0.5, 0.5)}[r["choice"]]
        hh[(l, rr)][0] += s[0]; hh[(l, rr)][1] += 1
        hh[(rr, l)][0] += s[1]; hh[(rr, l)][1] += 1
    print("     " + "".join(f"{j:>7s}" for j in items))
    for i in items:
        row = "".join(f"{(hh[(i,j)][0]/hh[(i,j)][1]):7.2f}" if hh[(i, j)][1] else "      -" for j in items)
        print(f"  {i:>3s}{row}")
    # per character
    print("\nPer-character ranking:")
    for ch in chars:
        sub = [r for r in recs if r["char"] == ch]
        if not sub:
            continue
        its = sorted({r["left"] for r in sub} | {r["right"] for r in sub})
        pc, _ = bradley_terry(sub, its)
        order = " > ".join(f"{i}({pc[i]:.1f})" for i in sorted(its, key=lambda k: -pc[k]))
        print(f"  {chars[ch]['display']:<20s} {order}")
    # judge agreement
    jrecs = {r["id"]: r for r in load(a.judge)} if True else {}
    both = [(r, jrecs[r["id"]]) for r in recs if r["id"] in jrecs]
    if both:
        agree = sum(1 for h, j in both if h["choice"] == j["choice"])
        nontie = [(h, j) for h, j in both if h["choice"] != "tie" and j["choice"] != "tie"]
        agree_nt = sum(1 for h, j in nontie if h["choice"] == j["choice"])
        # Cohen's kappa on the 3-way labels
        labs = ["left", "right", "tie"]
        n = len(both)
        po = agree / n
        ph = {l: sum(1 for h, _ in both if h["choice"] == l) / n for l in labs}
        pj = {l: sum(1 for _, j in both if j["choice"] == l) / n for l in labs}
        pe = sum(ph[l] * pj[l] for l in labs)
        kappa = (po - pe) / (1 - pe) if pe < 1 else float("nan")
        print(f"\nLLM judge agreement on {n} shared comparisons: {po*100:.0f}% "
              f"(non-tie: {agree_nt}/{len(nontie)} = {100*agree_nt/max(1,len(nontie)):.0f}%), Cohen's kappa {kappa:.2f}")
        pj_, _ = bradley_terry([j for _, j in both], items)
        print("Judge ranking: " + " > ".join(sorted(items, key=lambda k: -pj_[k])))
        print("Human ranking: " + " > ".join(sorted(items, key=lambda k: -p[k])))
    else:
        print("\n(no judge ratings yet — run eval/judge.py)")


if __name__ == "__main__":
    main()
