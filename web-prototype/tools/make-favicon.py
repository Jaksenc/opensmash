#!/usr/bin/env python3
"""Build the site favicons: a clean vector-style S from the Smash.fun wordmark.

Usage: python3 tools/make-favicon.py

Lifts the S's yellow face silhouette out of visual/assets/smash-the-weights-logo.png
(the faces of touching letters are split by erosion), cleans it, and rebuilds
the letter as flat layers: yellow face, red-orange stroke, black stroke.
Everything is drawn at 4x and anti-aliased on the way down. Writes:
  public/favicon.png (512), public/apple-touch-icon.png (180),
  public/favicon-16.png, public/favicon.ico (16 + 32).
"""
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'visual/assets/smash-the-weights-logo.png'
OUT = ROOT / 'public'

THEME_BLACK = (9, 8, 7)          # matches <meta name="theme-color">
TOUCH_TILE = (52, 44, 40)        # warm charcoal behind the letter on the iOS icon
FACE_TOP = (253, 238, 32)        # sampled from the wordmark's S
FACE_BOTTOM = (252, 201, 4)
STROKE_RED = (247, 79, 2)
ERODE = 16                       # erosion steps that split touching letter faces
FILL = 0.99                      # fraction of the tile the finished letter spans
# Stroke widths as a fraction of the face height. Slimmer at 16/32 px so the
# face keeps its pixels.
RED_FRAC, BLACK_FRAC = 0.055, 0.085
RED_FRAC_SMALL, BLACK_FRAC_SMALL = 0.05, 0.06
SS = 4                           # supersampling for the mask work

# ---- 1. isolate the S face -------------------------------------------------
im = Image.open(SRC).convert('RGBA')
a = np.array(im).astype(int)
r, g, b, al = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
yellow = (r > 190) & (g > 150) & (b < 120) & (al > 0)

seeds = ndimage.binary_erosion(yellow, iterations=ERODE)
seed_lab, n = ndimage.label(seeds)
seed_sizes = ndimage.sum(seeds, seed_lab, range(1, n + 1))
letters = [i + 1 for i, sz in enumerate(seed_sizes) if sz > 1500]
best_d = np.full(yellow.shape, np.inf)
lab = np.zeros(yellow.shape, dtype=int)
for i in letters:
    d = ndimage.distance_transform_edt(seed_lab != i)
    closer = d < best_d
    best_d[closer] = d[closer]
    lab[closer] = i
lab[~yellow] = 0
objs = ndimage.find_objects(lab)
s_id = min(letters, key=lambda i: objs[i - 1][1].start)  # leftmost letter = S
ys, xs = np.where(lab == s_id)
face = (lab == s_id)[ys.min():ys.max() + 1, xs.min():xs.max() + 1]

# ---- 2. clean the silhouette at SS x ---------------------------------------
face_h = face.shape[0] * SS
big = np.array(Image.fromarray((face * 255).astype(np.uint8), 'L')
               .resize((face.shape[1] * SS, face_h), Image.LANCZOS)) > 127
big = ndimage.binary_closing(big, iterations=SS)
big = ndimage.binary_opening(big, iterations=SS)
big = ndimage.gaussian_filter(big.astype(float), sigma=1.0 * SS) > 0.5

def layers(red_frac, black_frac):
    """Return an RGBA image of face + red stroke + black stroke, at SS x."""
    red_px = round(face_h * red_frac)
    black_px = round(face_h * black_frac)
    pad = red_px + black_px + 4 * SS
    f = np.pad(big, pad)
    dist = ndimage.distance_transform_edt(~f)           # 0 inside the face
    signed = ndimage.distance_transform_edt(f) - dist   # >0 inside, <0 outside
    aa = 0.6 * SS  # anti-aliasing width, in supersampled pixels
    def cover(edge):
        return np.clip((edge - dist) / aa + 0.5, 0, 1)
    c_face = np.clip(signed / aa + 0.5, 0, 1)
    c_red = cover(red_px)
    c_black = cover(red_px + black_px)

    h, w = f.shape
    out = np.zeros((h, w, 4), dtype=float)
    def paint(cov, rgb):
        cov = cov[..., None]
        out[..., :3] = out[..., :3] * (1 - cov) + np.array(rgb) * cov
        out[..., 3] = np.maximum(out[..., 3], cov[..., 0])
    paint(c_black, THEME_BLACK)
    paint(c_red, STROKE_RED)
    # Face: gentle top-to-bottom gradient like the wordmark.
    t = np.linspace(0, 1, h)[:, None, None]
    grad = np.array(FACE_TOP) * (1 - t) + np.array(FACE_BOTTOM) * t
    cov = c_face[..., None]
    out[..., :3] = out[..., :3] * (1 - cov) + grad * cov
    out[..., 3] = np.maximum(out[..., 3], c_face)
    out[..., 3] = out[..., 3] * 255
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), 'RGBA')

LETTER_BIG = layers(RED_FRAC, BLACK_FRAC)
LETTER_SMALL = layers(RED_FRAC_SMALL, BLACK_FRAC_SMALL)

# ---- 3. tiles --------------------------------------------------------------
def tile(size, background=None):
    letter = LETTER_SMALL if size <= 32 else LETTER_BIG
    # trim transparent padding so FILL is measured on the actual letter
    bbox = letter.getchannel('A').getbbox()
    letter = letter.crop(bbox)
    t = Image.new('RGBA', (size, size), (background or (0, 0, 0)) + (255 if background else 0,))
    gw, gh = letter.size
    scale = size * FILL / max(gw, gh)
    g = letter.resize((max(1, round(gw * scale)), max(1, round(gh * scale))), Image.LANCZOS)
    t.alpha_composite(g, ((size - g.width) // 2, (size - g.height) // 2))
    return t.convert('RGB') if background else t

tile(512).save(OUT / 'favicon.png', optimize=True)
tile(180, TOUCH_TILE).save(OUT / 'apple-touch-icon.png', optimize=True)
tile(16).save(OUT / 'favicon-16.png', optimize=True)
tile(32).save(OUT / 'favicon.ico', sizes=[(16, 16), (32, 32)], append_images=[tile(16)])
print('face', face.shape, 'letter', LETTER_BIG.size)
