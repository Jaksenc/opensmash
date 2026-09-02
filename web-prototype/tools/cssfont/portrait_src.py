"""Load the character-select portrait name strips as face-coverage / dark-alpha maps."""
import numpy as np, os
from PIL import Image
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIR = os.path.join(ROOT, 'asset-sources', 'css-font', 'portraits')
FACE = np.array([146, 139, 114], float)
NAMES = {'Mario': 'MARIO', 'Luigi': 'LUIGI', 'Donkey': 'D K', 'Samus': 'SAMUS', 'Fox': 'FOX', 'Kirby': 'KIRBY',
         'Link': 'LINK', 'Yoshi': 'YOSHI', 'Pikachu': 'PIKACHU', 'Ness': 'NESS', 'Captain': 'C.FALCON', 'Purin': 'JIGGLYPUFF'}
TILE_W, TILE_H = 45, 43

def load(name):
    a = np.array(Image.open(os.path.join(DIR, name + '.png')).convert('RGBA')).astype(float)
    rgb, A = a[..., :3], a[..., 3] / 255.0
    k = (rgb * FACE).sum(-1) / (FACE @ FACE)              # face colour fraction of the pixel colour
    resid = np.linalg.norm(rgb - k[..., None] * FACE, axis=-1)
    art = (A > 0) & (resid > 12)
    frame = np.zeros_like(art); frame[0, :] = True; frame[:, 0] = True; frame[:, TILE_W - 1] = True
    c = np.clip(k * A, 0, 1)                                # face coverage (colour * alpha)
    s = np.where(c < 0.999, (A - c) / np.maximum(1 - c, 1e-6), 0.0)
    return dict(c=c, s=s, A=A, rgb=rgb, art=art | frame, k=k)
