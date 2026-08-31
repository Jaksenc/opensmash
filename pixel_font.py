#!/usr/bin/env python3
"""Hand-authored pixel font for the CSS tile captions, in the vanilla
SSB64 caption style: cap height 7, single-pixel strokes, geometric caps,
flat tan fill (146,139,114). Letters that appear in the vanilla captions
(NESS, MARIO, JIGGLYPUFF, ...) are transcribed 1:1 from the tile dumps;
the rest (Q T V W Z, digits) are designed to the same grammar.

Rendering never resamples: fit is by tracking (1 -> 0), then a condensed
column-drop, then truncation. Every caption comes out with identical cap
height and stroke weight.
"""
from PIL import Image

FACE = (146, 139, 114, 255)   # vanilla flat tan (sampled from NESS strip)
OUTLINE = (52, 32, 22, 255)   # matches the baked caption edge on tiles
CAP = 7

# '#' = face pixel. All glyphs are CAP rows tall.
GLYPHS = {
    "A": ["..#..",
          ".#.#.",
          "#...#",
          "#####",
          "#...#",
          "#...#",
          "#...#"],
    "B": ["####.",
          "#...#",
          "#...#",
          "####.",
          "#...#",
          "#...#",
          "####."],
    "C": [".###.",
          "#...#",
          "#....",
          "#....",
          "#....",
          "#...#",
          ".###."],
    "D": ["####.",
          "#...#",
          "#...#",
          "#...#",
          "#...#",
          "#...#",
          "####."],
    "E": ["####",
          "#...",
          "#...",
          "###.",
          "#...",
          "#...",
          "####"],
    "F": ["####",
          "#...",
          "#...",
          "###.",
          "#...",
          "#...",
          "#..."],
    "G": [".###.",
          "#...#",
          "#....",
          "#.###",
          "#...#",
          "#...#",
          ".###."],
    "H": ["#...#",
          "#...#",
          "#...#",
          "#####",
          "#...#",
          "#...#",
          "#...#"],
    "I": ["#",
          "#",
          "#",
          "#",
          "#",
          "#",
          "#"],
    "J": ["...#",
          "...#",
          "...#",
          "...#",
          "...#",
          "#..#",
          ".##."],
    "K": ["#...#",
          "#..#.",
          "#.#..",
          "##...",
          "#.#..",
          "#..#.",
          "#...#"],
    "L": ["#...",
          "#...",
          "#...",
          "#...",
          "#...",
          "#...",
          "####"],
    "M": ["#.....#",
          "##...##",
          "#.#.#.#",
          "#..#..#",
          "#.....#",
          "#.....#",
          "#.....#"],
    "N": ["#....#",
          "##...#",
          "#.#..#",
          "#..#.#",
          "#...##",
          "#....#",
          "#....#"],
    "O": [".###.",
          "#...#",
          "#...#",
          "#...#",
          "#...#",
          "#...#",
          ".###."],
    "P": ["####.",
          "#...#",
          "#...#",
          "####.",
          "#....",
          "#....",
          "#...."],
    "Q": [".###.",
          "#...#",
          "#...#",
          "#...#",
          "#.#.#",
          "#..#.",
          ".##.#"],
    "R": ["####.",
          "#...#",
          "#...#",
          "####.",
          "#.#..",
          "#..#.",
          "#...#"],
    "S": [".###",
          "#...",
          "#...",
          ".##.",
          "...#",
          "...#",
          "###."],
    "T": ["#####",
          "..#..",
          "..#..",
          "..#..",
          "..#..",
          "..#..",
          "..#.."],
    "U": ["#...#",
          "#...#",
          "#...#",
          "#...#",
          "#...#",
          "#...#",
          ".###."],
    "V": ["#...#",
          "#...#",
          "#...#",
          "#...#",
          ".#.#.",
          ".#.#.",
          "..#.."],
    "W": ["#.....#",
          "#.....#",
          "#.....#",
          "#..#..#",
          "#.#.#.#",
          "##...##",
          "#.....#"],
    "X": ["#...#",
          ".#.#.",
          "..#..",
          "..#..",
          "..#..",
          ".#.#.",
          "#...#"],
    "Y": ["#...#",
          ".#.#.",
          "..#..",
          "..#..",
          "..#..",
          "..#..",
          "..#.."],
    "Z": ["####",
          "...#",
          "..#.",
          "..#.",
          ".#..",
          "#...",
          "####"],
    "0": [".###.",
          "#...#",
          "#..##",
          "#.#.#",
          "##..#",
          "#...#",
          ".###."],
    "1": [".#",
          "##",
          ".#",
          ".#",
          ".#",
          ".#",
          ".#"],
    "2": [".###.",
          "#...#",
          "....#",
          "..##.",
          ".#...",
          "#....",
          "#####"],
    "3": ["####.",
          "....#",
          "....#",
          ".###.",
          "....#",
          "....#",
          "####."],
    "4": ["#..#.",
          "#..#.",
          "#..#.",
          "#####",
          "...#.",
          "...#.",
          "...#."],
    "5": ["#####",
          "#....",
          "#....",
          "####.",
          "....#",
          "....#",
          "####."],
    "6": [".###.",
          "#....",
          "#....",
          "####.",
          "#...#",
          "#...#",
          ".###."],
    "7": ["#####",
          "....#",
          "...#.",
          "...#.",
          "..#..",
          "..#..",
          "..#.."],
    "8": [".###.",
          "#...#",
          "#...#",
          ".###.",
          "#...#",
          "#...#",
          ".###."],
    "9": [".###.",
          "#...#",
          "#...#",
          ".####",
          "....#",
          "....#",
          ".###."],
    ".": [".",
          ".",
          ".",
          ".",
          ".",
          ".",
          "#"],
    "-": ["...",
          "...",
          "...",
          "###",
          "...",
          "...",
          "..."],
    " ": ["..",
          "..",
          "..",
          "..",
          "..",
          "..",
          ".."],
}


def _condense(rows):
    """Drop one interior column where every row continues identically
    (straight horizontal runs) — a safe 1px squeeze for overflow names."""
    w = len(rows[0])
    for x in range(1, w - 1):
        if all(r[x] == r[x - 1] for r in rows):
            return [r[:x] + r[x + 1:] for r in rows]
    return rows


def _measure(text, tracking, glyphs):
    widths = [len(glyphs[c][0]) for c in text if c in glyphs]
    return sum(widths) + tracking * (len(widths) - 1) if widths else 0


def _paint(text, tracking, glyphs, face):
    im = Image.new("RGBA", (max(1, _measure(text, tracking, glyphs)), CAP),
                   (0, 0, 0, 0))
    px = im.load()
    x = 0
    for c in text:
        if c not in glyphs:
            continue
        rows = glyphs[c]
        for gy, row in enumerate(rows):
            for gx, cell in enumerate(row):
                if cell == "#":
                    px[x + gx, gy] = face
        x += len(rows[0]) + tracking
    return im


def _outline(im, color=OUTLINE):
    out = Image.new("RGBA", (im.width + 2, im.height + 2), (0, 0, 0, 0))
    mask = im.getchannel("A").point(lambda a: 255 if a > 0 else 0)
    plate = Image.new("RGBA", im.size, color)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx or dy:
                out.paste(plate, (1 + dx, 1 + dy), mask)
    out.alpha_composite(im, (1, 1))
    return out


def render_caption(text, max_width, face=FACE, outline=OUTLINE):
    """Caption bitmap (face + 1px outline) guaranteed <= max_width wide.
    Fit order: tracking 1 -> tracking 0 -> condensed glyphs -> truncate.
    Never resamples, so stroke weight and cap height are always exact."""
    text = "".join(c for c in text.upper() if c in GLYPHS)
    budget = max_width - 2                      # outline adds 2
    for glyphs in (GLYPHS,
                   {c: _condense(r) for c, r in GLYPHS.items()}):
        for tracking in (1, 0):
            if _measure(text, tracking, glyphs) <= budget:
                return _outline(_paint(text, tracking, glyphs, face), outline)
    while text and _measure(text, 0, GLYPHS) > budget:
        text = text[:-1]
    return _outline(_paint(text, 0, GLYPHS, FACE), outline)


# ---------------- bold panel variant (CSS card name, VS splash) ----------
# Derived from the regular set: cap 7 -> 9 by duplicating two straight rows,
# stroke 1 -> 2 by horizontal dilation. Matches the vanilla panel font's
# white face (subtle vertical falloff) with a 1px dark shadow at (-1,+1).

BOLD_FACE_TOP = (255, 255, 255, 255)
BOLD_FACE_BOT = (236, 236, 236, 255)
BOLD_SHADOW = (22, 22, 22, 255)
BOLD_CAP = 9

# Letterforms transcribed 1:1 from the vanilla panel-name dumps (face
# masks of MARIO/NESS/FOX/DK/SAMUS/LUIGI/KIRBY/PIKACHU/JIGGLYPUFF/YOSHI);
# Q T V W Z designed to the same grammar. Digits fall back to the
# emboldened caption set.
BOLD_OVERRIDES = {
    "A": ["...###...", "...###...", "..#####..", "..##.##..", "..##.##..",
          ".###.###.", ".#######.", "###...###", "###...###"],
    "B": ["######.", "#######", "##..###", "##..###", "######.",
          "###.###", "##..###", "#######", "######."],
    "C": [".####.", "######", "###...", "##....", "##....",
          "##....", "###...", "######", ".####."],
    "D": ["#####...", "#######.", "###.###.", "###..###", "###..###",
          "###..###", "########", "#######.", "#####..."],
    "E": ["#####", "#####", "##...", "###..", "#####",
          "#####", "##...", "#####", "#####"],
    "F": ["#####.", "######", "##....", "###...", "#####.",
          "#####.", "##....", "###...", "###..."],
    "G": [".####..", "######.", "###..##", "##.....", "##..###",
          "##..###", "###...#", ".######", "..#####"],
    "H": ["##..###", "##..###", "##..###", "##..###", "#######",
          "##..###", "##..###", "##..###", "##..###"],
    "I": ["###", ".##", ".##", ".##", ".##", ".##", ".##", ".##", ".##"],
    "J": ["..###", "...##", "...##", "...##", "...##",
          "...##", "#####", "#####", ".####"],
    "K": ["##..####", "##.####.", "##.####.", "#####...", "#####...",
          "#####...", "##.###..", "##..###.", "##..####"],
    "L": ["##....", "##....", "##....", "##....", "##....",
          "##....", "##....", "######", "######"],
    "M": [".###..###.", ".###..###.", ".########.", ".########.", ".########.",
          ".#########", ".##.##.###", "###.##.###", "###.#..###"],
    "N": ["##....###", "###...###", "####..###", "#####.###", "#########",
          "##.######", "##..#####", "###..####", "###...###"],
    "O": ["..#####..", ".#######.", "###...###", "###...###", "###....##",
          "###...###", ".###.####", ".#######.", "...####.."],
    "P": ["######.", ".######", ".##.###", ".##.###", ".######",
          ".#####.", ".##....", ".##....", ".##...."],
    "Q": ["..#####..", ".#######.", "###...###", "###...###", "###...###",
          "###.#.###", ".###.###.", ".#######.", "...###.##"],
    "R": ["######.", "#######", "##..###", "##..###", "#######",
          "######.", "##..##.", "##..###", "##...##"],
    "S": [".#####.", "######.", "###..#.", "####...", ".#####.",
          "...####", "#..###.", "######.", ".#####."],
    "T": ["#######", "#######", "..###..", "..###..", "..###..",
          "..###..", "..###..", "..###..", "..###.."],
    "U": ["##..###", "##..###", "##..###", "##..###", "##..###",
          "##..###", "##..###", "#######", ".#####."],
    "V": ["###..###", "###..###", "###..###", ".##..##.", ".##..##.",
          ".######.", "..####..", "..####..", "...##..."],
    "W": ["###.#..###", "###.##.###", ".##.##.###", ".#########", ".########.",
          ".########.", ".########.", ".###..###.", ".###..###."],
    "X": ["###..###", ".##.##..", ".######.", "..####..", "..####..",
          "..####..", ".######.", ".##.##..", "###..###"],
    "Y": ["###..###", ".##..##.", ".######.", "..####..", "..####..",
          "..####..", "..###...", "..###...", "..##...."],
    "Z": ["#######", "#######", "...###.", "..###..", "..###..",
          ".###...", "###....", "#######", "#######"],
}


def _embolden(rows):
    grown = []
    for i, r in enumerate(rows):
        grown.append(r)
        if i in (1, 5):          # straight rows in every glyph — safe to dup
            grown.append(r)
    out = []
    for r in grown:
        w = len(r)
        row = "".join("#" if r[x] == "#" or (x > 0 and r[x - 1] == "#") else "."
                      for x in range(w))
        out.append(row + ("#" if r[-1] == "#" else "."))
    return out


def bold_glyphs():
    g = {c: BOLD_OVERRIDES.get(c) or _embolden(r) for c, r in GLYPHS.items()}
    return g


def _dilate(rows):
    out = []
    for r in rows:
        w = len(r)
        row = "".join("#" if r[x] == "#" or (x > 0 and r[x - 1] == "#") else "."
                      for x in range(w))
        out.append(row + ("#" if r[-1] == "#" else "."))
    return out


def fat_glyphs():
    """Vanilla short-name weight: one extra dilation (~3px strokes)."""
    return {c: _dilate(r) for c, r in bold_glyphs().items()}


def _paint_bold(text, tracking, glyphs):
    w = max(1, _measure(text, tracking, glyphs))
    im = Image.new("RGBA", (w + 2, BOLD_CAP + 2), (0, 0, 0, 0))
    px = im.load()
    # collect face cells first so the shading can see neighbors
    cells = set()
    x = 2
    for c in text:
        if c not in glyphs:
            continue
        rows = glyphs[c]
        for gy, row in enumerate(rows):
            for gx, cell in enumerate(row):
                if cell == "#":
                    cells.add((x + gx, gy))
        x += len(rows[0]) + tracking
    # vanilla shading, measured off the YOSHI name dump:
    #  - stroke cores stay pure white; only the LEFT edge column of a
    #    stroke dims hard (~150) and the RIGHT edge dims slightly (~215)
    #    — that asymmetry is the baked anti-aliasing. No vertical AA.
    #  - a dark drop shadow falls LEFT and BELOW with fading alpha
    #    (nothing above or to the right of the letters).
    for (cx, cy) in cells:
        left_open = (cx - 1, cy) not in cells
        right_open = (cx + 1, cy) not in cells
        if left_open and right_open:
            v = 255                       # 1px stems stay bright
        elif left_open:
            v = 150
        elif right_open:
            v = 245
        else:
            v = 255
        px[cx, cy] = (v, v, v, 255)
    shadow = {}
    for (cx, cy) in cells:
        for dx, dy, a in ((-1, 0, 210), (-2, 0, 70), (0, 1, 210),
                          (-1, 1, 160), (0, 2, 90), (-1, 2, 50)):
            sx, sy = cx + dx, cy + dy
            if (sx, sy) not in cells:
                shadow[(sx, sy)] = max(shadow.get((sx, sy), 0), a)
    for (sx, sy), a in shadow.items():
        if 0 <= sx < im.width and 0 <= sy < im.height and px[sx, sy][3] == 0:
            px[sx, sy] = (0, 0, 0, a)
    return im


# Authentic letter patches: the face pixels (with their baked AA
# gradients) cut straight out of the vanilla panel-name dumps. Faces of
# adjacent letters never overlap — only shadows do — so a face-only
# filter (bright pixels) yields clean per-letter art. Shadows are
# regenerated uniformly at compose time.
PATCH_CUTS = {
    "A": ("samus", 13, 20), "B": ("kirby", 26, 33), "C": ("pikachu", 33, 40),
    "D": ("dk", 5, 14), "E": ("ness", 15, 21), "F": ("fox", 5, 11),
    "G": ("luigi", 24, 32), "H": ("yoshi", 30, 39), "I": ("yoshi", 39, 42),
    "J": ("purin", 4, 10), "K": ("dk", 16, 25), "L": ("luigi", 5, 11),
    "M": ("mario", 4, 15), "N": ("ness", 5, 14), "O": ("yoshi", 13, 23),
    "P": ("pikachu", 4, 12), "R": ("mario", 23, 31), "S": ("yoshi", 23, 30),
    "U": ("luigi", 12, 20), "X": ("fox", 22, 32), "Y": ("yoshi", 5, 13),
}
_PATCHES = None


def _mask_patch(rows):
    """Fallback patch for letters vanilla never shows: paint the binary
    mask with the measured face shading (no shadow; that's global)."""
    w = len(rows[0])
    im = Image.new("RGBA", (w, BOLD_CAP), (0, 0, 0, 0))
    px = im.load()
    cells = {(x, y) for y, r in enumerate(rows) for x, ch in enumerate(r) if ch == "#"}
    for (cx, cy) in cells:
        left_open = (cx - 1, cy) not in cells
        right_open = (cx + 1, cy) not in cells
        if left_open and right_open:
            v = 255
        elif left_open:
            v = 150
        elif right_open:
            v = 215
        else:
            v = 255
        px[cx, cy] = (v, v, v, 255)
    return im


def _load_patches():
    global _PATCHES
    if _PATCHES is not None:
        return _PATCHES
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    _PATCHES = {}
    for ch, (src, x0, x1) in PATCH_CUTS.items():
        im = Image.open(os.path.join(here, "website", "assets", "ui_refs", f"name_{src}.png")).convert("RGBA")
        px = im.load()
        w = min(x1, im.width) - x0
        p = Image.new("RGBA", (w, BOLD_CAP), (0, 0, 0, 0))
        pp = p.load()
        for y in range(BOLD_CAP):
            for x in range(w):
                r, g, b, a = px[x0 + x, 1 + y]
                if a > 60 and r > 100:
                    pp[x, y] = (r, g, b, 255)
        bb = p.getbbox()
        _PATCHES[ch] = p.crop((bb[0], 0, bb[2], BOLD_CAP)) if bb else p
    base = bold_glyphs()
    for ch in GLYPHS:
        if ch not in _PATCHES and ch not in " ":
            _PATCHES[ch] = _mask_patch(base[ch])
    return _PATCHES


def render_panel_name(text, max_width):
    """Bold white panel name (CSS card / VS splash), <= max_width wide.
    Authentic vanilla letter patches (baked AA), regenerated shadows,
    never resampled; fit by tracking, then truncation."""
    text = "".join(c for c in text.upper() if c in GLYPHS and c != " ")
    patches = _load_patches()

    def width_at(t, tr):
        ws = [patches[c].width for c in t]
        return sum(ws) + tr * (len(ws) - 1) if ws else 1

    budget = max_width - 2
    tracking = 1
    for tr in (1, 0):
        if width_at(text, tr) <= budget:
            tracking = tr
            break
    else:
        tracking = 0
        while text and width_at(text, 0) > budget:
            text = text[:-1]
    im = Image.new("RGBA", (width_at(text, tracking) + 2, BOLD_CAP + 2), (0, 0, 0, 0))
    x = 2
    for c in text:
        im.alpha_composite(patches[c], (x, 0))
        x += patches[c].width + tracking
    # vanilla drop shadow: dark, alpha-faded, LEFT and BELOW only
    px = im.load()
    solid = {(cx, cy) for cy in range(im.height) for cx in range(im.width)
             if px[cx, cy][3] > 0}
    shadow = {}
    for (cx, cy) in solid:
        for dx, dy, a in ((-1, 0, 210), (-2, 0, 70), (0, 1, 210),
                          (-1, 1, 160), (0, 2, 90), (-1, 2, 50)):
            s = (cx + dx, cy + dy)
            if s not in solid:
                shadow[s] = max(shadow.get(s, 0), a)
    for (sx, sy), a in shadow.items():
        if 0 <= sx < im.width and 0 <= sy < im.height and px[sx, sy][3] == 0:
            px[sx, sy] = (0, 0, 0, a)
    return im


if __name__ == "__main__":
    import sys
    for word in (sys.argv[1:] or ["WEIRDAL", "OBAMA", "MORITZ", "QUEEN", "JFLYNN"]):
        im = render_caption(word, 46)
        px = im.load()
        print(f"== {word} ({im.width}x{im.height})")
        for y in range(im.height):
            print("".join("#" if px[x, y][3] and px[x, y][:3] == FACE[:3]
                          else ("o" if px[x, y][3] else " ")
                          for x in range(im.width)))
