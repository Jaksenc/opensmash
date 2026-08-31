#!/usr/bin/env python3
"""Nudge a generated fighter atlas toward the vanilla Smash 64 Mario palette.

Targets the two systematic misses called out by visual QA:
  - shoes/hair: orange-tan  -> dark auburn/maroon boots
  - skin: pink              -> warm yellow tone

Classification is by hue/sat/value; corrections steer hue+saturation toward
the vanilla target while keeping each pixel's own value (shading survives).

Usage: recolor_atlas.py atlas.png [out.png]   (in-place if no out)
"""
import sys

import numpy as np
from PIL import Image


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    src = args[0]
    dst = args[1] if len(args) > 1 else src
    img = Image.open(src).convert("RGB")
    hsv = np.asarray(img.convert("HSV"), dtype=np.float32)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]

    if "--tripo" in sys.argv:
        # Tripo albedo already has vanilla-like cap/skin hues; only fix
        # the two verifier complaints: baked-AO gray gloves -> flat white,
        # chocolate shoes -> reddish maroon (dark browns only).
        glove = (S <= 45) & (V >= 140)
        V[glove] = np.clip(V[glove] * 1.25 + 20, 0, 255)
        S[glove] = S[glove] * 0.5
        shoe = (H >= 8) & (H <= 34) & (S >= 80) & (V >= 30) & (V <= 145)
        H[shoe] = H[shoe] * 0.3 + 5 * 0.7
        S[shoe] = np.clip(S[shoe] * 1.1, 0, 255)
        V[shoe] = np.clip(V[shoe] * 1.05, 0, 255)
        S[shoe] = np.clip(S[shoe] * 1.15, 0, 255)
        # flatten baked denim wrinkles: high-frequency V detail in the
        # blue overalls reads as dirt smudges at close camera
        try:
            import scipy.ndimage as ndi
            blue = (H >= 120) & (H <= 180) & (S >= 60)
            Vs = ndi.median_filter(V, size=9)
            V[blue] = V[blue] * 0.35 + Vs[blue] * 0.65
        except ImportError:
            blue = (H >= 120) & (H <= 180) & (S >= 60)
            mv = float(V[blue].mean()) if blue.any() else 128.0
            V[blue] = V[blue] * 0.55 + mv * 0.45

        # vanilla skin is paler than Tripo's warm tan
        skin = (H >= 8) & (H <= 28) & (S >= 60) & (S <= 160) & (V >= 150)
        S[skin] = S[skin] * 0.92
        H[skin] = H[skin] * 0.5 + 24 * 0.5  # toward vanilla warm yellow-tan
        V[skin] = np.clip(V[skin] * 1.05, 0, 255)

        # shirt/cap red reads darker than vanilla's bright red
        red = ((H <= 10) | (H >= 245)) & (S >= 120) & (V >= 110)  # V floor spares the shoes
        V[red] = np.clip(V[red] * 1.18 + 8, 0, 255)
        out = np.stack([H, S, V], -1).astype(np.uint8)
        Image.fromarray(out, "HSV").convert("RGB").save(dst)
        print(f"tripo recolor: gloves px={int(glove.sum())}, shoes px={int(shoe.sum())}, red px={int(red.sum())} -> {dst}")
        return

    # --- shoes / hair: brown-orange, mid value, saturated. Hue floor at 13
    # keeps shaded RED shirt/cap pixels (h<=10) out of the maroon remap.
    shoe = (H >= 13) & (H <= 34) & (S >= 110) & (V >= 45) & (V <= 215)
    # vanilla boot ~ RGB(110,45,40) -> HSV h≈2, s≈163
    H[shoe] = H[shoe] * 0.15 + 4 * 0.85
    S[shoe] = np.clip(S[shoe] * 0.55 + 150 * 0.45, 0, 255)
    V[shoe] = np.clip(V[shoe] * 0.82, 0, 255)

    # --- skin: pinkish, bright, mid saturation. S floor at 60 keeps the
    # warm-grey GLOVE shading out of the remap (tan-streaked gloves).
    skin = (H >= 4) & (H <= 30) & (S >= 60) & (S <= 130) & (V >= 165) & ~shoe
    # vanilla skin ~ RGB(238,205,145) -> HSV h≈27, s≈100
    H[skin] = H[skin] * 0.35 + 27 * 0.65
    S[skin] = np.clip(S[skin] * 0.6 + 100 * 0.4, 0, 255)
    V[skin] = np.clip(V[skin] * 1.04, 0, 255)

    # --- gloves: near-white with baked gray AO -> flat bright white
    # (vanilla gloves are unshaded white; baked shadows read "dirty")
    glove = (S <= 45) & (V >= 140)
    V[glove] = np.clip(V[glove] * 1.25 + 20, 0, 255)
    S[glove] = S[glove] * 0.5

    out = np.stack([H, S, V], -1).astype(np.uint8)
    Image.fromarray(out, "HSV").convert("RGB").save(dst)
    print(f"recolored: shoes/hair px={int(shoe.sum())}, skin px={int(skin.sum())} -> {dst}")


if __name__ == "__main__":
    main()
