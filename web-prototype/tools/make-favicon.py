#!/usr/bin/env python3
"""Build the site favicons from the F in the Smash.fun wordmark.

Usage: python3 tools/make-favicon.py

Segments the yellow letter faces in visual/assets/smash-the-weights-logo.png,
assigns every outline/glow pixel to its nearest letter, lifts the F (with its
own outline) inside a thick black F-shaped container, and writes:
  public/favicon.png (512), public/apple-touch-icon.png (180),
  public/favicon-16.png, public/favicon.ico (16 + 32).
"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'visual/assets/smash-the-weights-logo.png'
OUT = ROOT / 'public'
THEME_BLACK = (9, 8, 7)     # matches <meta name="theme-color">
TOUCH_TILE = (52, 44, 40)   # warm charcoal behind the burst on the iOS icon
GLYPH_FILL = 0.92           # fraction of tile the glyph's long side occupies
HALO_FRAC = 0.075           # black container thickness, fraction of glyph height

im = Image.open(SRC).convert('RGBA')
a = np.array(im).astype(int)
r, g, b, al = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
ink = (al > 0) & (np.maximum(np.maximum(r, g), b) > 40)
yellow = (r > 190) & (g > 150) & (b < 120) & (al > 0)

lab, n = ndimage.label(yellow)
sizes = ndimage.sum(yellow, lab, range(1, n + 1))
letters = [i + 1 for i, s in enumerate(sizes) if s > 2000]

# The F is the letter whose face starts right after the "." (x ~1332).
objs = ndimage.find_objects(lab)
f_id = min(letters, key=lambda i: abs(objs[i - 1][1].start - 1332))

# Voronoi-partition the ink by nearest yellow face so the F keeps only its own
# outline and glow, not the period's or the U's.
best_d = np.full(ink.shape, np.inf)
owner = np.zeros(ink.shape, dtype=int)
for i in letters:
    d = ndimage.distance_transform_edt(lab != i)
    closer = d < best_d
    best_d[closer] = d[closer]
    owner[closer] = i
f_mask = ink & (owner == f_id)
# Trim faint glow far from the face; keep the solid outline.
f_mask &= ndimage.distance_transform_edt(lab != f_id) < 34

ys, xs = np.where(f_mask)
y0, y1, x0_, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
glyph = np.array(im)[y0:y1, x0_:x1].copy()
glyph[..., 3] = np.where(f_mask[y0:y1, x0_:x1], glyph[..., 3], 0)
glyph = Image.fromarray(glyph.astype(np.uint8), 'RGBA')

# Black container: the glyph's silhouette dilated outward, drawn underneath.
halo_px = max(1, round(glyph.height * HALO_FRAC))
pad = halo_px + 2
alpha = np.array(glyph.getchannel('A')) > 0
alpha = np.pad(alpha, pad)
halo = ndimage.distance_transform_edt(~alpha) <= halo_px
halo_im = Image.fromarray((halo * 255).astype(np.uint8), 'L')
container = Image.new('RGBA', halo_im.size, THEME_BLACK + (255,))
container.putalpha(halo_im.filter(ImageFilter.GaussianBlur(0.6)))
container.alpha_composite(glyph, (pad, pad))
glyph = container

def tile(size, background=None):
    t = Image.new('RGBA', (size, size), (background or (0, 0, 0)) + (255 if background else 0,))
    gw, gh = glyph.size
    scale = size * GLYPH_FILL / max(gw, gh)
    g = glyph.resize((max(1, round(gw * scale)), max(1, round(gh * scale))), Image.LANCZOS)
    if size <= 32:
        g = g.filter(ImageFilter.UnsharpMask(radius=1, percent=120, threshold=0))
    t.alpha_composite(g, ((size - g.width) // 2, (size - g.height) // 2))
    return t.convert('RGB') if background else t

tile(512).save(OUT / 'favicon.png', optimize=True)
tile(180, TOUCH_TILE).save(OUT / 'apple-touch-icon.png', optimize=True)
tile(16).save(OUT / 'favicon-16.png', optimize=True)
tile(32).save(OUT / 'favicon.ico', sizes=[(16, 16), (32, 32)], append_images=[tile(16)])
print('glyph crop', glyph.size, 'from', (x0_, y0, x1, y1))
