#!/usr/bin/env python3
"""Build the SSB64 character-select PORTRAIT name font.

Source: the names baked into the 45x43 RGBA32 portrait tiles
(`llMNPlayersPortraits<Name>Sprite`, assets/css-font/portraits/*.png).
Tan face (146,139,114) 7 px tall with a black outline + soft shadow, drawn
over transparency; character art overlaps some letters (masked as unknown).

Every pixel decomposes into face coverage c and dark alpha s. Glyph faces are
cut exactly; same-letter faces that differ between names become variants;
dark pixels shared between neighbours are attributed with a fitted model and
then solved jointly (bounded least squares) so every name re-renders exactly
on all non-art pixels.
"""
import json, os, sys
import numpy as np
from scipy.ndimage import shift as ndshift, gaussian_filter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portrait_src as P

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = P.ROOT
FACE_Y0, FACE_Y1 = 3, 10        # face rows 3..9
BOX_Y0, BOX_Y1 = 2, 11          # glyph box rows 2..10: outline row above and below the 7 face rows (no soft shadow — the glow below is the portrait art)
BOX_H = BOX_Y1 - BOX_Y0
LEFT_SPILL, RIGHT_SPILL = 2, 2
QL = 255                        # 8-bit sprites
SPACE_ADVANCE = 2
# outline+shadow model: s = clip(g0*blur(face,s0) + g1*blur(shift(face,ox,oy),s1))
MODEL = dict(g0=2.5, s0=0.6, g1=0.0, ox=0.0, oy=1.0, s1=0.6)

# name -> [(letter, x0, x1, exceptions)]; exceptions = [(x, y0, y1)] extra pixels owned (rows inclusive)
# Overlaps: a pixel is owned by the LAST letter whose range/exception covers it unless an exception says otherwise.
LAYOUT = {
    'Mario':   [('M', 3, 10), ('A', 11, 17), ('R', 18, 23), ('I', 24, 25), ('O', 26, 32)],
    'Luigi':   [('L', 4, 7), ('U', 9, 13), ('I', 15, 16), ('G', 18, 24), ('I', 26, 27)],
    'Donkey':  [('D', 4, 9), ('K', 13, 19)],
    'Samus':   [('S', 3, 9), ('A', 9, 15), ('M', 16, 22), ('U', 24, 28), ('S', 29, 33)],
    'Fox':     [('F', 4, 8), ('O', 9, 15), ('X', 16, 22)],
    'Kirby':   [('K', 4, 9), ('I', 10, 11), ('R', 13, 18), ('B', 19, 23), ('Y', 24, 28)],
    'Link':    [('L', 4, 7), ('I', 9, 10), ('N', 12, 17), ('K', 19, 24)],
    'Yoshi':   [('Y', 4, 8), ('O', 10, 16), ('S', 18, 23), ('H', 24, 28), ('I', 30, 31)],
    'Pikachu': [('P', 4, 8), ('I', 10, 11), ('K', 13, 18), ('A', 19, 25), ('C', 26, 30), ('H', 31, 35), ('U', 37, 41)],
    'Ness':    [('N', 4, 9), ('E', 11, 14), ('S', 16, 20), ('S', 22, 26)],
    'Captain': [('C', 3, 6), ('.', 8, 9), ('F', 11, 15), ('A', 14, 20), ('L', 21, 24), ('C', 24, 28), ('O', 29, 34), ('N', 35, 40)],
}
# pixel ownership overrides for overlapping ranges: (name, x, y) -> letter index
OVERRIDE = {}
for x in (14, 15):
    for y in (3, 4): OVERRIDE[('Captain', x, y)] = 2      # F's bar over A
for y in (8, 9): OVERRIDE[('Captain', 24, y)] = 4         # L's foot under C
for y in range(3, 8): OVERRIDE[('Samus', 9, y)] = 0       # S's right side at col 9 rows 3-7; A's leg rows 8-9
TEXT = {n: P.NAMES[n] for n in LAYOUT}


def shadow_model(c):
    a = gaussian_filter(c, MODEL['s0'], mode='constant') * MODEL['g0']
    b = gaussian_filter(ndshift(c, (MODEL['oy'], MODEL['ox']), order=1, mode='constant'), MODEL['s1'], mode='constant') * MODEL['g1']
    return np.clip(a + b, 0, 1)


def q(v):
    return int(round(float(np.clip(v, 0, 1)) * QL)) * (255 // QL)


class Instance:
    def __init__(self, name, idx, letter, x0, x1):
        self.name, self.idx, self.letter, self.x0, self.x1 = name, idx, letter, x0, x1
        self.vid = None; self.fc = None; self.sm = None; self.partial = False

    def face_key(self):
        sub = self.fc[FACE_Y0:FACE_Y1, self.x0 - 1:self.x1 + 2]
        return (self.x1 - self.x0, np.round(sub, 4).tobytes())


def collect():
    sprites, instances = {}, []
    for name, layout in LAYOUT.items():
        d = P.load(name)
        c, s, A, art = d['c'], d['s'], d['A'], d['art']
        H, W = c.shape
        word = [Instance(name, i, L, x0, x1) for i, (L, x0, x1) in enumerate(layout)]
        owner = -np.ones((H, W), int)
        for i, (L, x0, x1) in enumerate(layout):
            owner[FACE_Y0:FACE_Y1, x0:x1 + 1] = np.where(owner[FACE_Y0:FACE_Y1, x0:x1 + 1] < 0, i, owner[FACE_Y0:FACE_Y1, x0:x1 + 1])
        # overlapping ranges: later letter wins only where the earlier has no face... use overrides
        for i, (L, x0, x1) in enumerate(layout):
            for j, (L2, x02, x12) in enumerate(layout):
                if j <= i: continue
                for x in range(max(x0, x02), min(x1, x12) + 1):
                    for y in range(FACE_Y0, FACE_Y1):
                        owner[y, x] = OVERRIDE.get((name, x, y), j if (name, x, y) not in OVERRIDE else OVERRIDE[(name, x, y)])
        for (nm, x, y), k in OVERRIDE.items():
            if nm == name: owner[y, x] = k
        # tan pixels outside every letter's face are character art, not text ...
        k = d['k']
        art = art | ((k > 0.05) & (A > 0) & (owner < 0))
        # ... but faint tan tints in the outline/shadow rows belong to the nearest letter
        for y, x in zip(*np.nonzero((c > 0.001) & ~art)):
            if not (BOX_Y0 <= y < BOX_Y1) or owner[y, x] >= 0: continue
            inrange = [k for k in range(len(word)) if word[k].x0 <= x <= word[k].x1]
            owner[y, x] = inrange[-1] if inrange else min(range(len(word)), key=lambda k: min(abs(x - word[k].x0), abs(x - word[k].x1)))
        for i, inst in enumerate(word):
            fc = np.zeros_like(c); m = (owner == i) & ~art
            fc[m] = c[m]; inst.fc = fc; inst.sm = shadow_model(fc)
            inst.partial = bool(((owner == i) & art).any())
        sprites[name] = dict(c=c, s=s, A=A, art=art, owner=owner)
        instances.extend(word)
    variants, by_letter = {}, {}
    for inst in instances:
        by_letter.setdefault(inst.letter, {}).setdefault(inst.face_key(), []).append(inst)
    for L, clusters in by_letter.items():
        ordered = sorted(clusters.values(), key=lambda lst: (any(i.partial for i in lst), -len(lst), lst[0].name))
        for k, lst in enumerate(ordered):
            vid = L if k == 0 else f'{L}.{k + 1}'
            for inst in lst: inst.vid = vid
            variants[vid] = lst
    return sprites, instances, variants


SHARES = {}


def compute_shares(sprites, instances):
    for name in LAYOUT:
        sp = sprites[name]; c, s, art = sp['c'], sp['s'], sp['art']
        insts = [i for i in instances if i.name == name]
        m = np.stack([i.sm for i in insts]); w = np.where(m >= 0.02, m, 0.0); tot = w.sum(0)
        share = np.zeros_like(m)
        for k in range(len(insts)):
            share[k] = np.where(tot > 0, w[k] / np.maximum(tot, 1e-9), 0.0) * s
        orphan = (tot == 0) & (s > 0) & ~art
        for y, x in zip(*np.nonzero(orphan)):
            k = sp['owner'][y, x]
            if k < 0: k = min(range(len(insts)), key=lambda k: min(abs(x - insts[k].x0), abs(x - insts[k].x1)))
            share[k, y, x] = s[y, x]
        share[:, (c >= 0.999) | art] = np.nan
        SHARES[name] = share


def build_glyph(vid, insts, sprites, all_instances, report):
    face_w = insts[0].x1 - insts[0].x0 + 1
    bw = face_w + LEFT_SPILL + RIGHT_SPILL
    samples = {}
    for inst in insts:
        sp = sprites[inst.name]; c = sp['c']; H, W = c.shape
        others = [o for o in all_instances if o.name == inst.name and o.idx != inst.idx]
        share = SHARES[inst.name][inst.idx]
        for y in range(BOX_Y0, BOX_Y1):
            for x in range(inst.x0 - LEFT_SPILL, inst.x1 + 1 + RIGHT_SPILL):
                if not (0 <= x < W): continue
                bx, by = x - inst.x0 + LEFT_SPILL, y - BOX_Y0
                own_face = inst.fc[y, x] > 0.001
                sh = share[y, x]
                if np.isnan(sh):
                    if own_face: samples.setdefault((bx, by), []).append((c[y, x], 0.0, 0.0))
                    continue
                m_oth = sum(o.sm[y, x] for o in others)
                samples.setdefault((bx, by), []).append((c[y, x] if own_face else 0.0, sh, m_oth))
    C = np.zeros((BOX_H, bw)); S = np.zeros((BOX_H, bw)); filled = np.zeros((BOX_H, bw), bool)
    for (bx, by), sm in samples.items():
        sm_sorted = sorted(sm, key=lambda v: v[2])
        C[by, bx] = sm_sorted[0][0]; S[by, bx] = sm_sorted[0][1]; filled[by, bx] = True
    sm = shadow_model(np.pad(C, ((2, 2), (2, 2))))[2:-2, 2:-2]
    nfill = int((~filled).sum())
    S[~filled] = sm[~filled]
    if nfill: report.append(f'{vid}: {nfill} hidden px filled from model')
    g = dict(w=bw, h=BOX_H, ox=-LEFT_SPILL, faceW=face_w,
             c=[round(float(v), 5) for v in C.reshape(-1)], s=[round(float(v), 5) for v in S.reshape(-1)],
             src=sorted({i.name for i in insts}), partial=any(i.partial for i in insts))
    add_ink(g); return g


def add_ink(g):
    """fractional ink bearings relative to the face origin: the outer edge of the
    first/last inked column, partial coverage counted as a partial pixel"""
    C = np.array(g['c']).reshape(g['h'], g['w']); cm = C.max(0)
    cols = np.nonzero(cm > 0.15)[0]
    if len(cols) == 0: cols = np.nonzero(cm > 0)[0]
    l, r = int(cols[0]), int(cols[-1])
    g['inkL'] = round(l + g['ox'] + (1 - float(cm[l])), 3)
    g['inkR'] = round(r + g['ox'] + float(cm[r]), 3)
    return g


def refine(glyphs, instances, sprites, reg=1e-3):
    from scipy.sparse import lil_matrix
    from scipy.optimize import lsq_linear
    var = {}
    for vid, g in glyphs.items():
        for k in range(len(g['s'])): var[(vid, k)] = len(var)
    rows, rhs = [], []
    for name in LAYOUT:
        sp = sprites[name]; c, s, art = sp['c'], sp['s'], sp['art']; H, W = c.shape
        insts = [i for i in instances if i.name == name]
        contrib = {}
        for inst in insts:
            g = glyphs[inst.vid]
            for by in range(g['h']):
                for bx in range(g['w']):
                    x = inst.x0 + g['ox'] + bx; y = by + BOX_Y0
                    if 0 <= x < W and 0 <= y < H: contrib.setdefault((y, x), []).append(var[(inst.vid, by * g['w'] + bx)])
        for (y, x), cols in contrib.items():
            if c[y, x] >= 0.999 or art[y, x]: continue
            rows.append(cols); rhs.append(min(s[y, x], 1.0))
    n, m = len(var), len(rows)
    Amat = lil_matrix((m + n, n)); b = np.zeros(m + n)
    for r, (cols, v) in enumerate(zip(rows, rhs)):
        for col in cols: Amat[r, col] = 1.0
        b[r] = v
    x0 = np.zeros(n)
    for (vid, k), col in var.items(): x0[col] = glyphs[vid]['s'][k]
    for col in range(n): Amat[m + col, col] = reg; b[m + col] = reg * x0[col]
    res = lsq_linear(Amat.tocsr(), b, bounds=(0, 1), lsmr_tol='auto', max_iter=8000)
    for (vid, k), col in var.items(): glyphs[vid]['s'][k] = round(float(res.x[col]), 6)
    return round(float(res.cost), 6)


def render(glyphs, seq, kern=None, positions=None):
    placed = []
    if positions is None:
        pen = 0
        for i, gid in enumerate(seq):
            if gid == ' ': pen += SPACE_ADVANCE; continue
            placed.append((gid, pen))
            g = glyphs[gid]
            if i + 1 < len(seq) and seq[i + 1] != ' ':
                nxt = glyphs[seq[i + 1]]
                pen = int(np.floor(pen + g['inkR'] + 1 + (kern or {}).get(gid[0] + seq[i + 1][0], 0) - nxt['inkL'] + 0.5))
            else:
                pen = int(np.floor(pen + g['inkR'] + 1 + 0.5))
    else:
        placed = list(zip(seq, positions))
    xmin = min(p + glyphs[g]['ox'] for g, p in placed); xmax = max(p + glyphs[g]['ox'] + glyphs[g]['w'] for g, p in placed)
    W = xmax - xmin; H = BOX_H
    C = np.zeros((H, W)); S = np.zeros((H, W))
    for gid, p in placed:
        g = glyphs[gid]; gc = np.array(g['c']).reshape(g['h'], g['w']); gs = np.array(g['s']).reshape(g['h'], g['w'])
        x0 = p + g['ox'] - xmin
        C[:, x0:x0 + g['w']] = np.maximum(C[:, x0:x0 + g['w']], gc); S[:, x0:x0 + g['w']] += gs
    S = np.minimum(S, 1.0)
    Aout = np.zeros((H, W), int); Iout = np.zeros((H, W), int)
    for y in range(H):
        for x in range(W):
            a = C[y, x] + S[y, x] * (1 - C[y, x])
            if a > 1e-9: Aout[y, x] = q(a); Iout[y, x] = q(C[y, x] / a)
    return Iout, Aout, xmin


def sprite_IA(sp):
    """original sprite as 8-bit face-fraction (k) and alpha, art pixels excluded"""
    A = np.round(sp['A'] * 255).astype(int)
    kk = np.where(sp['A'] > 0, sp['c'] / np.maximum(sp['A'], 1e-9), 0)
    I = np.round(np.clip(kk, 0, 1) * 255).astype(int)
    return I, A


def verify(glyphs, instances, sprites, report):
    total = 0
    for name in LAYOUT:
        insts = [i for i in instances if i.name == name]
        Ir, Ar, xmin = render(glyphs, [i.vid for i in insts], positions=[i.x0 for i in insts])
        sp = sprites[name]; I, A = sprite_IA(sp); art = sp['art']
        H, W = Ir.shape; oI = np.zeros_like(Ir); oA = np.zeros_like(Ar); unk = np.zeros((H, W), bool)
        for y in range(H):
            for x in range(W):
                sx, sy = x + xmin, y + BOX_Y0
                if 0 <= sx < I.shape[1] and 0 <= sy < I.shape[0]:
                    oI[y, x], oA[y, x] = I[sy, sx], A[sy, sx]; unk[y, x] = art[sy, sx]
                else: unk[y, x] = True
        diff = ((np.abs(oI - Ir) > 1) | (np.abs(oA - Ar) > 1)) & ((oA > 0) | (Ar > 0)) & ~unk
        n = int(diff.sum()); total += n
        report.append(f'VERIFY {name}: {n} px differ (tolerance ±1/255, art pixels excluded)')
        for y, x in zip(*np.nonzero(diff)):
            report.append(f'     px ({x + xmin},{y + BOX_Y0}) orig I/A {oI[y, x]}/{oA[y, x]} got {Ir[y, x]}/{Ar[y, x]}')
        if n:
            for y in range(H):
                report.append('   ' + ''.join('X' if diff[y, x] else ('*' if unk[y, x] else ('%x' % (oA[y, x] // 17) if oA[y, x] else '.')) for x in range(W)))
    return total


def pick_defaults(variants):
    defaults = {}
    for L in sorted({v[0].letter for v in variants.values()}):
        vids = [vid for vid, v in variants.items() if v[0].letter == L]
        clean = [v for v in vids if not any(i.partial for i in variants[v])] or vids
        def face(inst): return inst.fc[FACE_Y0:FACE_Y1, inst.x0 - 1:inst.x1 + 2]
        best = None
        for vid in clean:
            f = face(variants[vid][0]); tot = 0
            for other in vids:
                if other == vid: continue
                g = face(variants[other][0])
                tot += 1000 * len(variants[other]) if g.shape != f.shape else float(np.abs(f - g).sum()) * len(variants[other])
            if best is None or tot < best[0]: best = (tot, vid)
        defaults[L] = best[1]
    return defaults


def build_all():
    sprites, instances, variants = collect()
    compute_shares(sprites, instances)
    report, glyphs = [], {}
    for vid, insts in sorted(variants.items()):
        glyphs[vid] = build_glyph(vid, insts, sprites, instances, report)
    report.append(f'refine lsq cost: {refine(glyphs, instances, sprites)}')
    total = verify(glyphs, instances, sprites, report)
    report.append(f'TOTAL differing px across names: {total}')
    defaults = pick_defaults(variants)
    remap = {}
    for L, dv in defaults.items():
        others = sorted(v for v, i in variants.items() if i[0].letter == L and v != dv)
        remap[dv] = L
        for k, v in enumerate(others): remap[v] = f'{L}.{k + 2}'
    glyphs = {remap[v]: g for v, g in glyphs.items()}
    variants = {remap[v]: i for v, i in variants.items()}
    for inst in instances: inst.vid = remap[inst.vid]
    kern, obs = {}, {}
    for name in LAYOUT:
        if ' ' in TEXT[name]: continue
        insts = [i for i in instances if i.name == name]
        for a, b in zip(insts, insts[1:]):
            ga, gb = glyphs[a.vid], glyphs[b.vid]
            gap = (b.x0 + gb['inkL']) - (a.x0 + ga['inkR'])          # ink-to-ink distance (fractional px)
            obs.setdefault(a.letter + b.letter, []).append((round((gap - 1) * 4) / 4, name))
    for pair, lst in sorted(obs.items()):
        ks = sorted({k for k, _ in lst})
        if len(ks) > 1: report.append(f'PAIR {pair}: kerns {ks} ({[n for _, n in lst]})')
        k = float(np.median([k for k, _ in lst]))
        if abs(k) >= 0.25: kern[pair] = k
    layouts = {}
    for name in LAYOUT:
        insts = [i for i in instances if i.name == name]
        layouts[name] = dict(text=TEXT[name], glyphs=[[i.vid, i.x0] for i in insts], spriteW=P.TILE_W, spriteH=P.TILE_H)
    for vid, insts in sorted(variants.items()):
        report.append(f'variant {vid}: ' + ', '.join(f'{i.name}[{i.idx}]{"(art)" if i.partial else ""}' for i in insts))
    return dict(glyphs=glyphs, kern=kern, layouts=layouts, report=report, sprites=sprites, variants=variants, instances=instances)


if __name__ == '__main__':
    res = build_all()
    print('\n'.join(res['report']))
    print('kern', res['kern'])
    art = {n: [int(v) for v in res['sprites'][n]['art'][:16].reshape(-1)] for n in LAYOUT}
    json.dump(dict(glyphs=res['glyphs'], kern=res['kern'], layouts=res['layouts'], art=art), open(os.path.join(HERE, 'p_stage1.json'), 'w'))
