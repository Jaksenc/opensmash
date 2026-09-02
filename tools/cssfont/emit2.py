#!/usr/bin/env python3
"""Synthesize the missing letters (J Q T V W Z), repair art-damaged defaults,
and emit the final portrait name font:
  web-prototype/src/fonts/ssb-name-font-data.js   glyphs, kerning, layouts, reference sprites
  assets/css-font/letters/<L>.png (+@8x, sheet)    letters over black
Run after build2.py (reads p_stage1.json).
"""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build2 as B, portrait_src as P

HERE = B.HERE
OUT_DATA = os.path.join(B.ROOT, 'web-prototype', 'src', 'fonts', 'ssb-name-font-data.js')
OUT_LETTERS = os.path.join(B.ROOT, 'assets', 'css-font', 'letters')
d = json.load(open(os.path.join(HERE, 'p_stage1.json')))
G, KERN, LAYOUTS = d['glyphs'], d['kern'], d['layouts']
FW = B.FACE_Y0 - B.BOX_Y0          # face top row inside the box (=1)


def face_of(vid):
    g = G[vid]; C = np.array(g['c']).reshape(g['h'], g['w'])
    return C[FW:FW + 7, B.LEFT_SPILL:B.LEFT_SPILL + g['faceW']].copy()


def set_face(vid, face):
    g = G[vid]; C = np.array(g['c']).reshape(g['h'], g['w'])
    C[FW:FW + 7, B.LEFT_SPILL:B.LEFT_SPILL + g['faceW']] = face
    g['c'] = [round(float(v), 5) for v in C.reshape(-1)]


def hexrows(rows):
    h = len(rows); w = max(len(r) for r in rows); out = np.zeros((h, w))
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch != '.': out[y, x] = int(ch, 16) / 15
    return out


def band(w, h, p0, p1, thick, ss=16):
    out = np.zeros((h, w)); (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0; L = (dx * dx + dy * dy) ** 0.5; nx, ny = -dy / L, dx / L
    for y in range(h):
        for x in range(w):
            cnt = 0
            for sy in range(ss):
                for sx in range(ss):
                    px, py = x + (sx + .5) / ss, y + (sy + .5) / ss
                    t = ((px - x0) * dx + (py - y0) * dy) / (L * L); dist = abs((px - x0) * nx + (py - y0) * ny)
                    if 0 <= t <= 1 and dist <= thick / 2: cnt += 1
            out[y, x] = cnt / (ss * ss)
    return out


def make_glyph(face, src, synth=True):
    """face (7, faceW) coverage -> glyph with model outline/shadow"""
    fw = face.shape[1]; bw = fw + B.LEFT_SPILL + B.RIGHT_SPILL
    C = np.zeros((B.BOX_H, bw)); C[FW:FW + 7, B.LEFT_SPILL:B.LEFT_SPILL + fw] = np.clip(face, 0, 1)
    S = B.shadow_model(np.pad(C, 2))[2:-2, 2:-2]
    return B.add_ink(dict(w=bw, h=B.BOX_H, ox=-B.LEFT_SPILL, faceW=fw,
                c=[round(float(v), 5) for v in C.reshape(-1)], s=[round(float(v), 5) for v in S.reshape(-1)],
                src=src, synth=synth, partial=False))


def synth_all():
    out = {}
    # J: JIGGLYPUFF portrait (condensed cut, 1 px stem) -> widen the stem to the standard '5f' (1.3 px)
    pj = P.load('Purin'); cj = pj['c'][3:10, 3:7]         # cols 3..6
    J = np.zeros((7, 5)); J[:, 1:5] = cj
    J[:, 2] = np.maximum(J[:, 2], np.where(cj[:, 2] > 0.9, 5 / 15, 0))   # partial column left of the stem
    out['J'] = make_glyph(J, ['Purin'])
    # T: E's top bar (4 wide, extended to 5) + I stem
    E = face_of('E'); I = face_of('I')
    T = np.zeros((7, 5)); T[0, :] = 1.0; T[0, 4] = 10 / 15
    T[:, 1:3] = np.maximum(T[:, 1:3], I[:, 0:2] if I.shape[1] >= 2 else 1.0)
    out['T'] = make_glyph(T, ['E', 'I'])
    # V: A flipped, bar rows rebuilt as converging legs
    A = face_of('A')                                     # 7 wide
    V = A[::-1].copy()
    V[1] = hexrows(['5f4.4f5'])[0][:A.shape[1]] if A.shape[1] == 7 else V[1]
    V[2] = hexrows(['.f8.8f.'])[0][:A.shape[1]] if A.shape[1] == 7 else V[2]
    out['V'] = make_glyph(V, ['A'])
    # W: M flipped, +1 column in the middle
    M = face_of('M'); Mf = M[::-1]; mw = M.shape[1]; mid = mw // 2
    W = np.zeros((7, mw + 1)); W[:, :mid] = Mf[:, :mid]; W[:, mid + 1:] = Mf[:, mid:]
    W[:, mid] = np.maximum(Mf[:, mid - 1], Mf[:, mid])
    out['W'] = make_glyph(W, ['M'])
    # Z: bars + diagonal
    Z = np.zeros((7, 5)); Z[0, :] = 1.0; Z[6, :] = 1.0
    Z = np.maximum(Z, band(5, 7, (4.6, 0.8), (0.4, 6.2), 1.5))
    out['Z'] = make_glyph(Z, ['E', 'X'])
    # Q: O + tail
    O = face_of('O'); Q = np.zeros((7, O.shape[1] + 1)); Q[:, :O.shape[1]] = O
    Q = np.maximum(Q, band(Q.shape[1], 7, (O.shape[1] - 3.2, 4.4), (O.shape[1] + 0.4, 7.2), 1.4))
    out['Q'] = make_glyph(Q, ['O'])
    return out


if __name__ == '__main__':
    # repair: E's middle arm tip is under Ness's art; the standard E arm is 3 px (top/bottom are 4)
    E = face_of('E'); E[3, 3] = 0.0; set_face('E', E); B.add_ink(G['E']); G['E']['partial'] = False; G['E']['repaired'] = 'middle arm tip under art, set to 3 px like the sample rows'
    # repair: PIKACHU's H carries faint half-pixels above and below the crossbar
    # in the middle column (YOSHI's H has neither). Keep the untouched glyph for
    # the exact PIKACHU layout and clean the default.
    import copy
    G['H.pika'] = copy.deepcopy(G['H'])
    for lay in LAYOUTS.values():
        lay['glyphs'] = [['H.pika', x] if vid == 'H' else [vid, x] for vid, x in lay['glyphs']]
    H = face_of('H'); mid = H.shape[1] // 2
    for row in range(H.shape[0]):
        if H[row, mid] < 0.9: H[row, mid] = 0.0          # keep only the full crossbar row
    set_face('H', H); B.add_ink(G['H']); G['H']['repaired'] = 'stray tan in the counter column removed (PIKACHU art bleed); crossbar kept'
    # repair: the R's stem is heavier than every other stem in the face (second
    # column 0.67 vs 0.4). Slim the default R to the common stem weight; the
    # untouched glyph stays on the exact KIRBY layout.
    G['R.kirby'] = copy.deepcopy(G['R'])
    for lay in LAYOUTS.values():
        lay['glyphs'] = [['R.kirby', x] if vid == 'R' else [vid, x] for vid, x in lay['glyphs']]
    R = face_of('R')
    for row in range(R.shape[0]):
        if 0.5 < R[row, 1] < 0.9: R[row, 1] = 0.4
    set_face('R', R); B.add_ink(G['R']); G['R']['repaired'] = 'stem second column 0.67 -> 0.4 like P/B/K stems'
    for k, g in synth_all().items(): G[k] = g
    observed = set()
    for lay in LAYOUTS.values():
        t = lay['text'].replace(' ', '')
        observed.update(t[i:i + 2] for i in range(len(t) - 1))
    KERN_SYNTH = {}
    for pr in ['AV', 'VA', 'AW', 'WA', 'AY', 'YA', 'AT', 'TA', 'LT', 'LV', 'LW', 'LY', 'LJ', 'TJ', 'VO', 'WO', 'TO', 'OV', 'OW', 'OT',
               'PA', 'TY', 'YT', 'VY', 'YV', 'WY', 'YW', 'KO', 'RY', 'PJ', 'YO', 'FJ']:
        if pr not in KERN and pr not in observed: KERN_SYNTH[pr] = -1
    SPRITES = {}
    for name, text in P.NAMES.items():
        dd = P.load(name); A = np.round(dd['A'] * 255).astype(int)
        kk = np.where(dd['A'] > 0, dd['c'] / np.maximum(dd['A'], 1e-9), 0); I = np.round(np.clip(kk, 0, 1) * 255).astype(int)
        rgb = np.round(dd['rgb']).astype(int)
        strip = slice(0, 16)
        SPRITES[name] = dict(w=P.TILE_W, h=16, text=text,
                             ia=[int(v) for v in np.stack([I[strip], A[strip]], -1).reshape(-1)],
                             rgba=[int(v) for v in np.concatenate([rgb[strip], A[strip][..., None]], -1).reshape(-1)],
                             art=d['art'].get(name, [int(v) for v in dd['art'][strip].reshape(-1)]))
    data = dict(version=2, source='MNPlayersPortraits name strips', faceColor=[146, 139, 114],
                capHeight=7, boxH=B.BOX_H, faceRow=B.FACE_Y0, boxRow=B.BOX_Y0, leftSpill=B.LEFT_SPILL, rightSpill=B.RIGHT_SPILL,
                spaceAdvance=B.SPACE_ADVANCE, defaultGap=1, textOrigin=dict(x=4, y=3),
                glyphs=G, kern=KERN, kernSynth=KERN_SYNTH, layouts=LAYOUTS, sprites=SPRITES)
    os.makedirs(os.path.dirname(OUT_DATA), exist_ok=True)
    with open(OUT_DATA, 'w') as f:
        f.write('// Generated by tools/cssfont/emit2.py — do not edit by hand.\n')
        f.write('// SSB64 character-select name font, extracted from the MNPlayersPortraits tiles.\n')
        f.write('export const SSB_NAME_FONT = ' + json.dumps(data, separators=(',', ':')) + ';\nexport default SSB_NAME_FONT;\n')
    print('wrote', OUT_DATA, os.path.getsize(OUT_DATA) // 1024, 'KB')
    # letters over black
    os.makedirs(OUT_LETTERS, exist_ok=True)
    FACE = np.array([146, 139, 114], float)

    def to_rgb(g):
        C = np.array(g['c']).reshape(g['h'], g['w']); S = np.minimum(np.array(g['s']).reshape(g['h'], g['w']), 1)
        a = C + S * (1 - C); k = np.where(a > 1e-9, C / np.maximum(a, 1e-9), 0)
        rgb = (k[..., None] * FACE * a[..., None]).round().astype(np.uint8)    # over black
        rgba = np.concatenate([(k[..., None] * FACE).round().astype(np.uint8), (a * 255).round().astype(np.uint8)[..., None]], -1)
        return Image.fromarray(rgb, 'RGB'), Image.fromarray(rgba, 'RGBA')
    letters = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ') + ['.']
    cellw = max(G[L]['w'] for L in letters) + 2; cellh = B.BOX_H + 4
    sheet = Image.new('RGB', (cellw * 14, cellh * 2), (0, 0, 0))
    for i, L in enumerate(letters):
        rgb, rgba = to_rgb(G[L]); nm = 'period' if L == '.' else L
        rgb.save(os.path.join(OUT_LETTERS, f'{nm}.png')); rgba.save(os.path.join(OUT_LETTERS, f'{nm}_rgba.png'))
        rgb.resize((rgb.width * 8, rgb.height * 8), Image.NEAREST).save(os.path.join(OUT_LETTERS, f'{nm}@8x.png'))
        sheet.paste(rgb, ((i % 14) * cellw + 1, (i // 14) * cellh + 3))
    sheet = sheet.resize((sheet.width * 8, sheet.height * 8), Image.NEAREST); dr = ImageDraw.Draw(sheet)
    for i, L in enumerate(letters):
        dr.text(((i % 14) * cellw * 8 + 2, (i // 14) * cellh * 8), L + ('*' if G[L].get('synth') else ''), fill=(255, 90, 90))
    sheet.save(os.path.join(OUT_LETTERS, 'sheet@8x.png'))
    print('letters ->', OUT_LETTERS)
