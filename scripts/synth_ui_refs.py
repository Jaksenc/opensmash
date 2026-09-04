#!/usr/bin/env python3
"""Synthesize local stand-ins for the ROM-derived panel-name dumps.

pixel_font._load_patches() cuts authentic letter faces out of
web-prototype/visual/assets/ui_refs/name_<fighter>.png (game-derived,
gitignored, rebuilt from your own ROM by tools/derive_from_rom.py).
Without a ROM those dumps don't exist and render_panel_name() fails.

This draws each PATCH_CUTS slot with the hand-authored bold mask from
pixel_font itself (same binary letterforms the no-dump fallback path uses),
so the extractor recovers identical faces. Quality matches the fallback
path everywhere; swapping in real dumps later is a drop-in upgrade
(delete the files, re-derive from ROM).

Output: web-prototype/visual/assets/ui_refs/name_{mario,fox,dk,samus,luigi,
  yoshi,kirby,pikachu,purin,ness}.png (gitignored, local only).
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "pipeline"))
from pixel_font import PATCH_CUTS, bold_glyphs, BOLD_CAP  # noqa: E402
from PIL import Image  # noqa: E402

OUT = os.path.join(HERE, "web-prototype", "visual", "assets", "ui_refs")


def main():
    os.makedirs(OUT, exist_ok=True)
    glyphs = bold_glyphs()
    by_src = {}
    for ch, (src, x0, x1) in PATCH_CUTS.items():
        by_src.setdefault(src, []).append((ch, x0, x1))
    for src, slots in sorted(by_src.items()):
        w = max(x1 for _, _, x1 in slots) + 2
        im = Image.new("RGBA", (w, BOLD_CAP + 2), (0, 0, 0, 0))
        px = im.load()
        for ch, x0, _ in slots:
            for gy, row in enumerate(glyphs[ch]):
                for gx, cell in enumerate(row):
                    if cell == "#":
                        px[x0 + gx, 1 + gy] = (255, 255, 255, 255)
        p = os.path.join(OUT, f"name_{src}.png")
        im.save(p)
        print(f"synth {p}")
    print("done. Real dumps from tools/derive_from_rom.py replace these 1:1.")


if __name__ == "__main__":
    main()
