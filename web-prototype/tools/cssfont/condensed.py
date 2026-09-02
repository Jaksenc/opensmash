"""Condensed cut of the character-select name font.

The JIGGLYPUFF tile uses a narrower cut of the same face: 1 px stems, bowls
and counters squeezed to a single column, letters 1-2 columns narrower and
set tighter (P-U and F-F touch, the L foot tucks under the Y). The eight
letters that tile shows (J I G L Y P U F) are taken from it exactly; the rest
are drawn by hand in the same idiom (hex coverage rows, 7 rows tall).
"""
import numpy as np
import portrait_src as P

# JIGGLYPUFF tile: letter -> face columns (rows 3..9)
PURIN_CUT = {'J': (3, 6), 'I': (8, 8), 'G': (10, 13), 'L': (20, 22), 'Y': (22, 26), 'P': (28, 31), 'U': (32, 35), 'F': (37, 39)}
# pixel ownership fixes for the L/Y overlap at column 22: L owns its foot row, Y the rest
PURIN_FIX = {'L': {(22, 9): 1.0, (22, 3): 0.0, (22, 4): 0.0}, 'Y': {(22, 9): 0.0}}
PURIN_TEXT = 'JIGGLYPUFF'
PURIN_LAYOUT = [('J', 3), ('I', 8), ('G', 10), ('G', 15), ('L', 20), ('Y', 22), ('P', 28), ('U', 32), ('F', 37), ('F', 40)]

# Hand-drawn condensed letters (same idiom as the tile: 'f' = full, '3'/'7'/'9'/'c' = partial)
HAND = {
    'A': ['.ff.', 'f33f', 'f..f', 'ffff', 'f..f', 'f..f', 'f..f'],
    'B': ['fff3', 'f.9c', 'f.9c', 'fff3', 'f.9c', 'f.9c', 'fff3'],
    'C': ['4ff4', 'f76f', 'f3..', 'f3..', 'f3..', 'f76f', '4ff4'],
    'D': ['fff3', 'f.9c', 'f.9c', 'f.9c', 'f.9c', 'f.9c', 'fff3'],
    'E': ['ffb', 'f..', 'f..', 'ff.', 'f..', 'f..', 'ffb'],
    'H': ['f..f', 'f..f', 'f..f', 'ffff', 'f..f', 'f..f', 'f..f'],
    'K': ['f..f', 'f.f7', 'ff7.', 'ff..', 'ff7.', 'f.f7', 'f..f'],
    'M': ['f...f', 'ff.ff', 'f7f7f', 'f.f.f', 'f...f', 'f...f', 'f...f'],
    'N': ['f..f', 'fc.f', 'f9af', 'f.9f', 'f.cf', 'f..f', 'f..f'],
    'O': ['4ff4', 'f76f', 'f33f', 'f33f', 'f33f', 'f76f', '4ff4'],
    'Q': ['4ff4.', 'f76f.', 'f33f.', 'f33f.', 'f37f.', 'f7fb.', '4ff7c'],
    'R': ['fff3', 'f.9c', 'f.9c', 'fff3', 'f.f.', 'f.9c', 'f..f'],
    'S': ['4ff4', 'f73.', 'f3..', '4ff4', '..3f', '.37f', '4ff4'],
    'T': ['fff', '.f.', '.f.', '.f.', '.f.', '.f.', '.f.'],
    'V': ['f...f', 'f9.9f', '7f.f7', '.f5f.', '.afa.', '.5f5.', '..f..'],
    'W': ['f...f', 'f...f', 'f...f', 'f.f.f', 'f.f.f', 'f7f7f', '.f.f.'],
    'X': ['f9.9f', '7f.f7', '.afa.', '..f..', '.afa.', '7f.f7', 'f9.9f'],
    'Z': ['ffff', '..9c', '..f7', '.9c.', '.f7.', '9c..', 'ffff'],
    '.': ['.', '.', '.', '.', '.', 'f', 'f'],
}

# pairs set tighter than the default one-column gap (measured on the tile: P-U and
# F-F touch, L-Y overlap; the rest are the usual diagonal pairs)
KERN = {'PU': -1, 'FF': -1, 'LY': -2, 'LT': -1, 'LV': -1, 'AV': -1, 'VA': -1, 'AY': -1, 'YA': -1,
        'AT': -1, 'TA': -1, 'AW': -1, 'WA': -1, 'TJ': -1, 'LJ': -1, 'FA': -1, 'PA': -1}


# Extra-narrow cut: 3 px letters (M/W 5, N 4, I 1) for names even the condensed
# cut cannot hold. Same 7 px height and 1 px outline; drawn by hand.
NARROW = {
    'A': ['.f.', 'f.f', 'f.f', 'fff', 'f.f', 'f.f', 'f.f'],
    'B': ['ff.', 'f.f', 'f.f', 'ff.', 'f.f', 'f.f', 'ff.'],
    'C': ['.ff', 'f..', 'f..', 'f..', 'f..', 'f..', '.ff'],
    'D': ['ff.', 'f.f', 'f.f', 'f.f', 'f.f', 'f.f', 'ff.'],
    'E': ['fff', 'f..', 'f..', 'ff.', 'f..', 'f..', 'fff'],
    'F': ['fff', 'f..', 'f..', 'ff.', 'f..', 'f..', 'f..'],
    'G': ['.ff', 'f..', 'f..', 'f.f', 'f.f', 'f.f', '.ff'],
    'H': ['f.f', 'f.f', 'f.f', 'fff', 'f.f', 'f.f', 'f.f'],
    'I': ['f', 'f', 'f', 'f', 'f', 'f', 'f'],
    'J': ['..f', '..f', '..f', '..f', '..f', 'f.f', '.f.'],
    'K': ['f.f', 'f.f', 'ff.', 'ff.', 'ff.', 'f.f', 'f.f'],
    'L': ['f..', 'f..', 'f..', 'f..', 'f..', 'f..', 'fff'],
    'M': ['f...f', 'ff.ff', 'f.f.f', 'f.f.f', 'f...f', 'f...f', 'f...f'],
    'N': ['f..f', 'fc.f', 'f9af', 'f.9f', 'f.cf', 'f..f', 'f..f'],
    'O': ['.f.', 'f.f', 'f.f', 'f.f', 'f.f', 'f.f', '.f.'],
    'P': ['ff.', 'f.f', 'f.f', 'ff.', 'f..', 'f..', 'f..'],
    'Q': ['.f.', 'f.f', 'f.f', 'f.f', 'f.f', 'fbf', '.f9'],
    'R': ['ff.', 'f.f', 'f.f', 'ff.', 'f.f', 'f.f', 'f.f'],
    'S': ['.ff', 'f..', 'f..', '.f.', '..f', '..f', 'ff.'],
    'T': ['fff', '.f.', '.f.', '.f.', '.f.', '.f.', '.f.'],
    'U': ['f.f', 'f.f', 'f.f', 'f.f', 'f.f', 'f.f', '.f.'],
    'V': ['f.f', 'f.f', 'f.f', 'f.f', '.f.', '.f.', '.f.'],
    'W': ['f...f', 'f...f', 'f...f', 'f.f.f', 'f.f.f', 'f.f.f', '.f.f.'],
    'X': ['f.f', 'f.f', '.f.', '.f.', '.f.', 'f.f', 'f.f'],
    'Y': ['f.f', 'f.f', 'f.f', '.f.', '.f.', '.f.', '.f.'],
    'Z': ['fff', '..f', '..f', '.f.', 'f..', 'f..', 'fff'],
    '.': ['.', '.', '.', '.', '.', 'f', 'f'],
}


def build_narrow(make_glyph, hexrows):
    return dict(glyphs={L: make_glyph(hexrows(rows), ['hand'], synth=True) for L, rows in NARROW.items()},
                kern={}, defaultGap=1, spaceAdvance=2)


def build(make_glyph, hexrows):
    out = {}
    pj = P.load('Purin'); c = pj['c']
    for L, (x0, x1) in PURIN_CUT.items():
        face = c[3:10, x0:x1 + 1].copy()
        for (x, y), v in PURIN_FIX.get(L, {}).items():
            face[y - 3, x - x0] = v
        out[L] = make_glyph(np.clip(face, 0, 1), ['Purin'], synth=False)
    for L, rows in HAND.items():
        out[L] = make_glyph(hexrows(rows), ['hand'], synth=True)
    return dict(glyphs=out, kern=KERN, defaultGap=1, spaceAdvance=2,
                layout=dict(text=PURIN_TEXT, glyphs=[[L, x] for L, x in PURIN_LAYOUT]))
