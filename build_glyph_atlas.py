#!/usr/bin/env python3
"""Build the two SSB64 letter atlases from the roster sprite dumps in
website/assets/ui_refs/ (name_*.png = bold white panel font, tile_*.png = thin tan tile
captions). The roster covers 21 letters; Q,T,V,W,Z are synthesized from
existing strokes with regenerated drop shadows.

Outputs website/assets/ui_refs/glyph_<ord>.png (panel) and
website/assets/ui_refs/tileglyph_<ord>.png
(tile). Deterministic — safe to re-run whenever the dumps change.
"""
import glob
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(HERE, "website", "assets", "ui_refs")


# ---------------- bold panel font (IA8 dumps: white face, dark shadow) ---

def bold_src(name):
    return Image.open(os.path.join(REFS, f"name_{name}.png"))

BOLD_CUTS = {  # letter -> (source sprite, x0, x1); cuts at top-gap midpoints
 "M": ("mario", 4,15), "A": ("mario",15,23), "R": ("mario",23,32),
 "I": ("mario",32,36), "O": ("mario",36,46),
 "F": ("fox", 4,12), "X": ("fox",21,33),
 "D": ("dk", 4,14), "K": ("dk",16,26),
 "S": ("samus",5,14),
 "E": ("ness",15,22), "N": ("ness",4,15),
 "P": ("pikachu",4,11), "C": ("pikachu",30,38), "H": ("pikachu",38,46),
 "U": ("pikachu",48,57),
 "J": ("purin",3,10), "G": ("purin",13,21), "L": ("purin",27,33),
 "Y": ("purin",34,40), "B": ("kirby",29,38),
 # L's right edge stops before Y's first column (a 1px Y sliver otherwise
 # shows whenever L ends a word)
}


def clean_lead(g, cols=1, dark=140):
    px = g.load()
    for x in range(min(cols, g.width)):
        for y in range(g.height):
            p = px[x, y]
            if p[3] > 0 and p[0] <= dark:
                px[x, y] = (0, 0, 0, 0)
    return g


def face_of(g, bright=140):
    """white face only, shadow stripped"""
    out = Image.new("RGBA", g.size, (0, 0, 0, 0))
    px, op = g.load(), out.load()
    for x in range(g.width):
        for y in range(g.height):
            p = px[x, y]
            if p[3] > 128 and p[0] > bright:
                op[x, y] = p
    return out


def with_shadow(face, color=(38, 38, 38, 255)):
    out = Image.new("RGBA", (face.width + 1, face.height), (0, 0, 0, 0))
    mask = face.getchannel("A").point(lambda a: 255 if a > 100 else 0)
    plate = Image.new("RGBA", face.size, color)
    out.paste(plate, (1, 1), mask)
    out.alpha_composite(face, (0, 0))
    return out


def synth_bold(atlas):
    # Q: O plus a tail stroke
    O = atlas["O"].copy()
    q = Image.new("RGBA", (O.width + 1, 16), (0, 0, 0, 0))
    q.alpha_composite(O, (0, 0))
    qp = q.load()
    w = O.width
    for dx, dy in ((-6, 7), (-5, 7), (-5, 8), (-4, 8), (-4, 9), (-3, 9), (-3, 10), (-2, 10)):
        qp[w + dx, dy] = (255, 255, 255, 255)
    for dx, dy in ((-4, 10), (-3, 11), (-2, 11), (-1, 11)):
        qp[w + dx, dy] = (45, 45, 45, 255)
    atlas["Q"] = q
    # T: F's top bar + I's stem centered
    F, I = face_of(atlas["F"]), face_of(atlas["I"])
    t = Image.new("RGBA", (F.width, 16), (0, 0, 0, 0))
    t.alpha_composite(F.crop((0, 0, F.width, 4)), (0, 0))
    t.alpha_composite(I.crop((0, 3, I.width, 16)), ((F.width - I.width) // 2, 3))
    atlas["T"] = with_shadow(t)
    # V: Y's upper fork stretched to the full letter height
    Yf = face_of(atlas["Y"])
    bb = Yf.getbbox()
    fork = Yf.crop((bb[0], bb[1], bb[2], bb[1] + max(3, (bb[3] - bb[1]) * 3 // 5)))
    v = Image.new("RGBA", (Yf.width, 16), (0, 0, 0, 0))
    v.alpha_composite(fork.resize((fork.width, bb[3] - bb[1]), Image.NEAREST), (0, bb[1]))
    atlas["V"] = with_shadow(v)
    # W: M flipped vertically (face only), shadow regenerated
    Mf = face_of(atlas["M"])
    bb = Mf.getbbox()
    core = Mf.crop(bb).transpose(Image.FLIP_TOP_BOTTOM)
    wim = Image.new("RGBA", (Mf.width, 16), (0, 0, 0, 0))
    wim.alpha_composite(core, (bb[0], bb[1]))
    atlas["W"] = with_shadow(wim)
    # Z: N rotated a quarter turn (its diagonal + stems become Z)
    Nf = face_of(atlas["N"])
    bb = Nf.getbbox()
    core = Nf.crop(bb).transpose(Image.ROTATE_90)
    hh = bb[3] - bb[1]
    core = core.resize((core.width, hh), Image.NEAREST) if core.height != hh else core
    z = Image.new("RGBA", (core.width + 1, 16), (0, 0, 0, 0))
    z.alpha_composite(core, (0, bb[1]))
    atlas["Z"] = with_shadow(z)
    return atlas


# ---------------- thin tile caption font (tan on dark tiles) -------------

TILE_STRINGS = {"mario": "MARIO", "fox": "FOX", "dk": "DK", "samus": "SAMUS",
                "luigi": "LUIGI", "link": "LINK", "yoshi": "YOSHI",
                "captain": "C.FALCON", "kirby": "KIRBY", "pikachu": "PIKACHU",
                "purin": "JIGGLYPUFF", "ness": "NESS"}
TILE_GH = 10


def tan(r, g, b):
    return g > r * 0.7 and b > r * 0.5


def tile_mask_cols(im):
    px = im.load()
    return [sum(1 for y in range(1, TILE_GH)
                if (px[x, y][0] + px[x, y][1] + px[x, y][2]) // 3 > 105 and tan(*px[x, y][:3]))
            for x in range(im.width)]


def tile_segment(cols, n):
    W = len(cols)
    xs = [x for x in range(W) if cols[x] > 0]
    if not xs:
        return []
    x0, x1 = min(xs), max(xs) + 1
    span = x1 - x0
    cuts = [x0]
    for i in range(1, n):
        t = x0 + round(span * i / n)
        cuts.append(min(range(max(x0 + 1, t - 2), min(x1 - 1, t + 3)),
                        key=lambda x: (cols[x], abs(x - t))))
    cuts.append(x1)
    return [(cuts[i], cuts[i + 1]) for i in range(n)]


def tile_cut(im, a, b):
    g = Image.new("RGBA", (max(1, b - a), TILE_GH), (0, 0, 0, 0))
    px, gp = im.load(), g.load()
    for x in range(a, b):
        for y in range(TILE_GH):
            r, gr, bl, al = px[x, y]
            lum = (r + gr + bl) // 3
            if lum > 105 and tan(r, gr, bl):
                gp[x - a, y] = (r, gr, bl, 255)
            elif lum > 80 and tan(r, gr, bl):
                gp[x - a, y] = (r, gr, bl, 110)
    # despeckle: drop pixels with no orthogonal neighbor
    for x in range(g.width):
        for y in range(TILE_GH):
            if gp[x, y][3]:
                n = sum(1 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                        if 0 <= x + dx < g.width and 0 <= y + dy < TILE_GH and gp[x + dx, y + dy][3])
                if n == 0:
                    gp[x, y] = (0, 0, 0, 0)
    return g


def synth_tile(atlas):
    TAN = (215, 200, 165, 255)
    O = atlas["O"].copy()
    q = Image.new("RGBA", (O.width + 1, TILE_GH), (0, 0, 0, 0))
    q.alpha_composite(O, (0, 0))
    qp = q.load()
    for dx, dy in ((q.width - 4, 7), (q.width - 3, 8), (q.width - 2, 9)):
        qp[dx, dy] = TAN
    atlas["Q"] = q
    F, I = atlas["F"], atlas["I"]
    t = Image.new("RGBA", (F.width, TILE_GH), (0, 0, 0, 0))
    t.alpha_composite(F.crop((0, 0, F.width, 5)), (0, 0))
    t.alpha_composite(I.crop((0, 4, I.width, TILE_GH)), ((F.width - I.width) // 2, 4))
    atlas["T"] = t
    Y = atlas["Y"]
    bb = Y.getbbox()
    if bb:
        fork = Y.crop((bb[0], bb[1], bb[2], bb[1] + max(2, (bb[3] - bb[1]) * 3 // 5)))
        v = Image.new("RGBA", (Y.width, TILE_GH), (0, 0, 0, 0))
        v.alpha_composite(fork.resize((fork.width, bb[3] - bb[1]), Image.NEAREST), (0, bb[1]))
        atlas["V"] = v
    M = atlas["M"]
    bb = M.getbbox()
    if bb:
        wim = Image.new("RGBA", (M.width, TILE_GH), (0, 0, 0, 0))
        wim.alpha_composite(M.crop(bb).transpose(Image.FLIP_TOP_BOTTOM), (bb[0], bb[1]))
        atlas["W"] = wim
    N = atlas["N"]
    bb = N.getbbox()
    if bb:
        core = N.crop(bb).transpose(Image.ROTATE_90)
        hh = bb[3] - bb[1]
        z = Image.new("RGBA", (core.width, TILE_GH), (0, 0, 0, 0))
        z.alpha_composite(core.resize((core.width, hh), Image.NEAREST), (0, bb[1]))
        atlas["Z"] = z
    return atlas


def main():
    bold = {}
    for ch, (src, x0, x1) in BOLD_CUTS.items():
        bold[ch] = clean_lead(bold_src(src).crop((x0, 0, x1, 16)).copy())
    bold = synth_bold(bold)

    tile = {}
    order = ["purin", "captain", "luigi", "yoshi", "kirby", "samus", "link",
             "ness", "dk", "pikachu", "mario", "fox"]  # later wins
    for name in order:
        txt = TILE_STRINGS[name]
        im = Image.open(os.path.join(REFS, f"tile_{name}.png"))
        segs = tile_segment(tile_mask_cols(im), len(txt))
        if len(segs) != len(txt):
            continue
        for (a, b), ch in zip(segs, txt):
            tile[ch] = tile_cut(im, a, b)
    # fox overrides give the widest F/O/X (3-letter tile)
    fox = Image.open(os.path.join(REFS, "tile_fox.png"))
    tile["F"], tile["O"], tile["X"] = tile_cut(fox, 4, 10), tile_cut(fox, 10, 17), tile_cut(fox, 17, 25)
    # yoshi gives clean Y/H; link gives clean L/I (JIGGLYPUFF is too dense)
    yo = Image.open(os.path.join(REFS, "tile_yoshi.png"))
    tile["Y"], tile["H"] = tile_cut(yo, 4, 10), tile_cut(yo, 25, 31)
    lk = Image.open(os.path.join(REFS, "tile_link.png"))
    tile["L"], tile["I"] = tile_cut(lk, 4, 10), tile_cut(lk, 11, 15)
    tile = synth_tile(tile)

    for pref in ("glyph", "tileglyph"):
        for f in glob.glob(os.path.join(REFS, f"{pref}_*.png")):
            os.remove(f)
    for ch, im in bold.items():
        im.save(os.path.join(REFS, f"glyph_{ord(ch)}.png"))
    for ch, im in tile.items():
        im.save(os.path.join(REFS, f"tileglyph_{ord(ch)}.png"))
    print("bold:", "".join(sorted(bold)), "| tile:", "".join(sorted(tile)))


if __name__ == "__main__":
    main()
