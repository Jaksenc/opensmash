#!/usr/bin/env python3
"""Animation-pose stretch metric: how badly does a converted bundle's mesh
deform over the REAL poses the game visits?

For every dumped frame of the eval-tour replay (eval/streams/fk<K>.json,
from run_eval.py --dump), the bundle's skinned verts are posed exactly as
the engine poses them, and every triangle edge is compared to its
bind-pose length.

Two numbers, catching the two visible failure classes:
  * EXCESS STRETCH — edge ratios divided by the length the skeleton
    itself predicts (weight-blended per-joint scale: the engine animates
    joint scale for effects — mario's 15/16 hit 4.5x in the tour — and
    vanilla meshes scale right along, so raw ratios would blame correct
    behavior). 1.0 = deforms exactly as the skeleton dictates; 3.0 = the
    smear the eye reads as a torn sleeve.
  * BOUNDARY GAP — for skeleton-adjacent dominant-part pairs, how far the
    two vert sets pull apart over the tour vs bind (in %% of character
    height).
  * BONE COVERAGE — for every limb bone, the worst over the tour of "how
    far is the nearest mesh vert from each point along the bone", vs the
    same measure at bind. THE samus signature: sleeve geometry rigidly
    glued to the chest never stretches — the arm bone simply extends into
    empty space and the limb visually vanishes. Stretch cannot see it
    (validated 2026-08-28: 6 chars x 4 targets, stretch ranked samus BEST
    while humans rank it worst; coverage is the discriminating number).

This is the numeric gate of the retarget-quality loop:
  stretch_eval (seconds, every converter change)
    -> ab_variants blind eval (perceptual, for changes that move this)
    -> in-game spot check.
The objective was chosen because the postsmooth fix was originally
validated on exactly this number (p99.9 6.9x -> 3.1x); the T-pose sheet
smears are this same quantity at a synthetic worst-case pose.

Usage:
  stretch_eval.py bundle.json eval/streams/fk3.json [--player 0]
                  [--stride 2] [--thresh 3.0] [--json out.json]
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.dirname(HERE)

# eval-tour move labels (capture_clip.py convention: screenshot/FRM frame
# = replay tick + 4); a frame maps to the nearest labeled tick at or below
TOUR_LABELS = sorted({
    459: "walk", 531: "run-left", 594: "run", 679: "walk-left",
    729: "idle", 812: "jab", 852: "jab2", 906: "ftilt", 976: "utilt",
    1049: "crouch", 1116: "fsmash", 1196: "usmash", 1275: "jump",
    1294: "air", 1344: "land", 1385: "jump2", 1396: "nair", 1409: "air",
    1459: "shield", 1526: "taunt", 1584: "idle"}.items())


def label_for(t):
    lbl = "pre-tour"
    for f, name in TOUR_LABELS:
        if t >= f:
            lbl = name
        else:
            break
    return lbl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("stream", help="eval/streams/fk<K>.json pose dump")
    ap.add_argument("--player", default="0")
    ap.add_argument("--target", default="mario",
                    help="skeleton the bundle was retargeted onto "
                         "(names skels/<t>.profile.json; maps the gap "
                         "pairs into target joint numbering)")
    ap.add_argument("--min-t", type=int, default=0,
                    help="skip frames before this tic (425 = skip the "
                         "spawn/entry animation — samus unfurls from the "
                         "morph ball, an extreme pose that dominates "
                         "worst-case numbers)")
    ap.add_argument("--stride", type=int, default=2,
                    help="use every Nth dumped frame")
    ap.add_argument("--thresh", type=float, default=3.0,
                    help="stretch ratio counted as a visible defect")
    ap.add_argument("--json", default=None,
                    help="also write machine-readable results here")
    args = ap.parse_args()

    sk = json.load(open(args.bundle))["skinned"]
    stream = json.load(open(args.stream))
    frames = [f for f in stream["frames"][::args.stride]
              if f["t"] >= args.min_t]

    # bind data
    bind = {int(j): (np.array(f["o"]), np.array(f["R"]))
            for j, f in sk["bind_frames"].items()}
    joints = sorted(bind)
    jix = {j: k for k, j in enumerate(joints)}
    P = np.array([v[0:3] for v in sk["verts"]])            # (N,3) bind pos
    N = len(P)
    W = np.zeros((N, len(joints)))
    dom = np.zeros(N, dtype=int)
    for i, v in enumerate(sk["verts"]):
        if not v[8]:
            continue
        for j, w in v[8]:
            if j in jix:
                W[i, jix[j]] += w
        tot = W[i].sum()
        if tot > 0:
            W[i] /= tot
        dom[i] = joints[int(W[i].argmax())]
    tris = np.array(sk["tris"], dtype=int)                 # (T,3)
    E = np.stack([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]], 1)  # (T,3,2)
    bl = np.linalg.norm(P[E[..., 0]] - P[E[..., 1]], axis=-1)  # (T,3) bind lens
    bl = np.maximum(bl, 1e-6)

    # precompute per-joint bind inverse and (p - bo) once
    Binv = {j: np.linalg.inv(bind[j][1]) for j in joints}
    Prel = {j: P - bind[j][0] for j in joints}

    # boundary-gap pairs: ONLY skeleton-adjacent part boundaries, in
    # canonical numbering mapped through the target profile. Anything
    # else that happens to touch at bind (samus folds her hands together)
    # separates legitimately under animation and must not be scored.
    CHAIN = [(6, 8), (8, 9), (9, 10), (6, 12), (6, 14), (14, 15), (15, 16),
             (6, 19), (19, 20), (20, 22), (6, 24), (24, 25), (25, 27)]
    if args.target != "mario":
        prof = json.load(open(os.path.join(
            PIPE, "skels", f"{args.target}.profile.json")))["map"]
        c2t = {int(k): int(v) for k, v in prof.items()}
        CHAIN = [(c2t.get(a, a), c2t.get(b, b)) for a, b in CHAIN]
    dom_verts = {j: np.nonzero(dom == j)[0] for j in joints}
    gap_pairs = sorted({(min(a, b), max(a, b)) for a, b in CHAIN
                        if a != b and len(dom_verts.get(a, ())) and
                        len(dom_verts.get(b, ()))})
    height = float(P[:, 1].max() - P[:, 1].min()) or 1.0

    def pair_gap(pos, a, b):
        A, B = pos[dom_verts[a]], pos[dom_verts[b]]
        # min inter-set distance (sampled for speed on big parts)
        A = A[::3] if len(A) > 200 else A
        B = B[::3] if len(B) > 200 else B
        d2 = ((A[:, None, :] - B[None, :, :]) ** 2).sum(-1)
        return float(np.sqrt(d2.min()))

    bind_gap = {pr: pair_gap(P, *pr) for pr in gap_pairs}
    gap_max = {pr: 0.0 for pr in gap_pairs}

    # bone-coverage: limb bones in canonical numbering -> target ids
    BONES = [("L-uparm", 8, 9), ("L-forearm", 9, 10),
             ("R-uparm", 14, 15), ("R-forearm", 15, 16),
             ("L-thigh", 19, 20), ("L-shin", 20, 22),
             ("R-thigh", 24, 25), ("R-shin", 25, 27)]
    if args.target != "mario":
        BONES = [(nm, c2t.get(a, a), c2t.get(b, b)) for nm, a, b in BONES]
    BONES = [(nm, a, b) for nm, a, b in BONES
             if a != b and a in bind and b in bind]
    NSAMP = 7

    def bone_cover(pos, bind_frames):
        # worst nearest-vert distance along each bone segment
        out = {}
        for nm, a, b in BONES:
            oa, ob = bind_frames[a], bind_frames[b]
            ts = np.linspace(0.15, 0.85, NSAMP)
            pts = oa[None, :] * (1 - ts[:, None]) + ob[None, :] * ts[:, None]
            d = np.sqrt(((pos[None, ::2, :] - pts[:, None, :]) ** 2)
                        .sum(-1)).min(1)
            out[nm] = float(d.max())
        return out

    cover_bind = bone_cover(P, {j: bind[j][0] for j in joints})
    cover_max = {nm: 0.0 for nm, _, _ in BONES}
    cover_arg = {nm: 0 for nm, _, _ in BONES}
    # persistence: eyes read SUSTAINED loss (old-samus slab through the
    # whole walk), not single-frame transients mid-swing — count frames
    # over threshold, don't just track the max
    cover_bad = {nm: 0 for nm, _, _ in BONES}
    cover_n = 0
    gap_arg = {pr: 0 for pr in gap_pairs}

    tri_max = np.zeros(len(tris))            # worst stretch per tri, ever
    tri_arg = np.zeros(len(tris), dtype=int)  # frame t where it happened
    samples = []                              # per-frame p99 for the report
    all_ratios = []                           # subsampled global distribution
    for fr in frames:
        pl = fr["players"].get(args.player)
        if pl is None:
            continue
        jf = {int(j): d for j, d in pl["joints"].items()}
        pos = np.zeros((N, 3))
        vscale = np.zeros(N)                  # weight-blended joint scale
        for j in joints:
            d = jf.get(j)
            if d is None:                     # joint missing this frame
                pos += W[:, jix[j], None] * P
                vscale += W[:, jix[j]]
                continue
            M = Binv[j] @ np.array(d["R"])
            sj = float(np.linalg.norm(M, axis=1).mean())
            pos += W[:, jix[j], None] * (Prel[j] @ M + np.array(d["o"]))
            vscale += W[:, jix[j]] * sj
        el = np.linalg.norm(pos[E[..., 0]] - pos[E[..., 1]], axis=-1)
        # skeleton-predicted length: bind length x mean endpoint scale
        pred = bl * (vscale[E[..., 0]] + vscale[E[..., 1]]) / 2.0
        r = el / np.maximum(pred, 1e-6)
        r /= np.median(r)                     # cancel residual global scale
        tmax = r.max(1)                       # (T,) per-tri worst edge
        upd = tmax > tri_max
        tri_arg[upd] = fr["t"]
        tri_max = np.maximum(tri_max, tmax)
        samples.append((fr["t"], float(np.percentile(tmax, 99))))
        all_ratios.append(tmax[::7])          # subsample for global stats
        gscale = float(np.median(vscale))
        jscale = {}
        for j in joints:
            d = jf.get(j)
            jscale[j] = float(np.linalg.norm(
                (Binv[j] @ np.array(d["R"])), axis=1).mean()) if d else 1.0
        for pr in gap_pairs:
            # skip joint-scale FX moments (the engine balloons hands 4x
            # for effects; vanilla geometry does the same — not a defect)
            if any(abs(jscale[j] / gscale - 1.0) > 0.15 for j in pr):
                continue
            g = (pair_gap(pos, *pr) / max(gscale, 1e-6) - bind_gap[pr]) / height
            if g > gap_max[pr]:
                gap_max[pr] = g
                gap_arg[pr] = fr["t"]
        jo = {}
        for j in joints:
            d = jf.get(j)
            jo[j] = np.array(d["o"]) if d else bind[j][0]
        cover_n += 1
        for nm, a, b in BONES:
            if abs(jscale[a] / gscale - 1) > 0.15 or \
               abs(jscale[b] / gscale - 1) > 0.15:
                continue
            oa, ob = jo[a], jo[b]
            ts = np.linspace(0.15, 0.85, NSAMP)
            pts = oa[None, :] * (1 - ts[:, None]) + ob[None, :] * ts[:, None]
            d = np.sqrt(((pos[None, ::2, :] - pts[:, None, :]) ** 2)
                        .sum(-1)).min(1)
            c = (float(d.max()) / max(gscale, 1e-6) - cover_bind[nm]) / height
            if c > 0.015:
                cover_bad[nm] += 1
            if c > cover_max[nm]:
                cover_max[nm] = c
                cover_arg[nm] = fr["t"]

    allr = np.concatenate(all_ratios)
    pct = {p: float(np.percentile(allr, p)) for p in (50, 95, 99, 99.9)}
    bad = tri_max > args.thresh
    n_bad = int(bad.sum())

    # blame: for each offending tri, the joint pair its verts straddle
    from collections import Counter
    blame = Counter()
    for ti in np.nonzero(bad)[0]:
        ds = sorted({int(dom[i]) for i in tris[ti]})
        blame[tuple(ds) if len(ds) > 1 else (ds[0],)] += 1
    move_blame = Counter(label_for(int(tri_arg[ti])) for ti in np.nonzero(bad)[0])

    name = os.path.basename(args.bundle)
    print(f"== {name} vs {os.path.basename(args.stream)} "
          f"({len(frames)} frames, {len(tris)} tris)")
    print(f"  stretch p50={pct[50]:.2f}  p95={pct[95]:.2f}  "
          f"p99={pct[99]:.2f}  p99.9={pct[99.9]:.2f}  max={tri_max.max():.1f}")
    print(f"  tris ever past {args.thresh:g}x: {n_bad} "
          f"({100.0*n_bad/len(tris):.1f}%)")
    if blame:
        print("  blame (joint sets of offending tris):")
        for pair, c in blame.most_common(8):
            print(f"    {'+'.join(str(j) for j in pair):<12} {c}")
        print("  worst moves:", ", ".join(
            f"{m}({c})" for m, c in move_blame.most_common(6)))
        worst = sorted(samples, key=lambda x: -x[1])[:5]
        print("  worst frames (t, p99):",
              ", ".join(f"{t}={v:.1f}" for t, v in worst))
    print("  bone coverage loss (worst %% height @ move / %% of frames past 1.5%%):")
    for nm, c in sorted(cover_max.items(), key=lambda kv: -kv[1]):
        frac = 100.0 * cover_bad[nm] / max(cover_n, 1)
        print(f"    {nm:<10} {100*c:5.1f}%  @ {label_for(cover_arg[nm]):<10} "
              f"sustained {frac:5.1f}%")
    top_gaps = sorted(gap_max.items(), key=lambda kv: -kv[1])[:6]
    print("  boundary gaps (part pair: max growth %% height @ move):")
    for pr, g in top_gaps:
        print(f"    {pr[0]}+{pr[1]:<4} {100*g:5.1f}%  @ {label_for(gap_arg[pr])}")
    if args.json:
        json.dump({"bundle": args.bundle, "stream": args.stream,
                   "pct": pct, "n_tris": len(tris), "n_bad": n_bad,
                   "thresh": args.thresh, "max": float(tri_max.max()),
                   "blame": {"+".join(map(str, k)): v
                             for k, v in blame.most_common()},
                   "move_blame": dict(move_blame),
                   "gaps": {f"{a}+{b}": [round(100*g, 2), label_for(gap_arg[(a, b)])]
                            for (a, b), g in sorted(gap_max.items(),
                                                    key=lambda kv: -kv[1])},
                   "cover": {nm: [round(100*c, 2), label_for(cover_arg[nm]),
                                  round(100.0*cover_bad[nm]/max(cover_n, 1), 2)]
                             for nm, c in sorted(cover_max.items(),
                                                 key=lambda kv: -kv[1])}},
                  open(args.json, "w"), indent=1)
        print(f"  -> {args.json}")


if __name__ == "__main__":
    main()
