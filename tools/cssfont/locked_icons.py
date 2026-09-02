#!/usr/bin/env python3
"""Search-glass and plus icons in the style of the character-select question
mark (MNPlayersPortraits QuestionMark: 45x43 IA8 coverage mask, ~4 px stroke,
23 px tall, tinted in-game with prim (C4,B9,A9) / env (5B,41,33)).
Writes assets/css-font/locked/{SearchGlass,Plus}.png (white + alpha, same
format as the extracted question mark) and a tinted preview sheet."""
import os, sys
import numpy as np
from PIL import Image
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'assets', 'css-font', 'locked')
W, H, SS = 45, 43, 12
PRIM = np.array([0xC4, 0xB9, 0xA9], float); ENV = np.array([0x5B, 0x41, 0x33], float)


def coverage(sdf):
    """sdf(x, y) -> signed distance (inside < 0) in pixel units; box-filtered coverage"""
    cov = np.zeros((H, W))
    off = (np.arange(SS) + 0.5) / SS
    for y in range(H):
        for x in range(W):
            px = x + off[None, :]; py = y + off[:, None]
            cov[y, x] = (sdf(px, py) <= 0).mean()
    return cov


def ring(cx, cy, r, t):
    return lambda x, y: np.abs(np.hypot(x - cx, y - cy) - r) - t / 2


def segment(x0, y0, x1, y1, t):
    def f(x, y):
        dx, dy = x1 - x0, y1 - y0; L2 = dx * dx + dy * dy
        u = np.clip(((x - x0) * dx + (y - y0) * dy) / L2, 0, 1)
        return np.hypot(x - (x0 + u * dx), y - (y0 + u * dy)) - t / 2
    return f


def union(*fs):
    return lambda x, y: np.min([f(x, y) for f in fs], axis=0)


def frame(mask):
    """sprite: white face, alpha = coverage, plus the tile's one-texel frame"""
    a = np.round(np.clip(mask, 0, 1) * 255)
    a[0, :] = a[-1, :] = a[:, 0] = a[:, -1] = 0xCC
    I = np.round(np.clip(mask, 0, 1) * 255); I[0, :] = I[-1, :] = I[:, 0] = I[:, -1] = 0
    rgba = np.stack([I, I, I, a], -1).astype(np.uint8)
    return Image.fromarray(rgba, 'RGBA')


def tinted(sprite_rgba, bg):
    """in-game look: texel I lerps env->prim, alpha = texel A, over the fire bg"""
    s = np.array(sprite_rgba).astype(float); b = np.array(bg.convert('RGBA')).astype(float)[..., :3]
    k = s[..., 0:1] / 255; a = s[..., 3:4] / 255
    col = ENV + (PRIM - ENV) * k
    out = b * (1 - a) + col * a
    return Image.fromarray(out.round().astype(np.uint8), 'RGB')


# question mark geometry: rows 10..32 (23 px), centred on x≈22, stroke ≈ 4 px
STROKE = 4.0
CX, TOP, BOT = 22.5, 10.0, 33.0
# --- search glass: lens ring upper-left, handle to lower-right
glass = union(ring(20.0, 19.5, 5.5, STROKE - 0.5), segment(24.3, 23.8, 29.3, 29.3, STROKE - 0.6))
# --- plus: two bars, same overall height as the '?'
plus = union(segment(CX, TOP + 3.5, CX, BOT - 3.5, STROKE), segment(CX - 7.5, 21.5, CX + 7.5, 21.5, STROKE))

# overall icon scale about the tile's icon centre (2/3 of the '?' size)
SCALE = 0.8
ICX, ICY = 22.5, 21.5
def scaled(f):
    return lambda x, y: f(ICX + (x - ICX) / SCALE, ICY + (y - ICY) / SCALE) * SCALE
glass, plus = scaled(glass), scaled(plus)

os.makedirs(OUT, exist_ok=True)
icons = {'SearchGlass': frame(coverage(glass)), 'Plus': frame(coverage(plus))}
for name, im in icons.items(): im.save(os.path.join(OUT, f'{name}.png'))
q = Image.open(os.path.join(OUT, 'QuestionMark.png')).convert('RGBA')
bg = Image.open(os.path.join(ROOT, 'assets', 'css-font', 'portraits', 'FireBg.png'))
black = Image.new('RGBA', (W, H), (0, 0, 0, 255))
cells = [q, icons['SearchGlass'], icons['Plus']]
Z = 6
sheet = Image.new('RGB', ((W + 3) * 3 * Z, (H + 3) * 2 * Z), (20, 20, 22))
for i, im in enumerate(cells):
    for row, back in enumerate([bg, black]):
        t = tinted(im, back).resize((W * Z, H * Z), Image.NEAREST)
        sheet.paste(t, (i * (W + 3) * Z, row * (H + 3) * Z))
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(OUT, 'preview.png')
sheet.save(out); print('wrote', out)
