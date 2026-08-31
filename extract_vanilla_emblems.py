#!/usr/bin/env python3
"""Dump the game's ten series emblems out of relocData file 20 into a
reference sheet (website/assets/ui_refs/emblem_ref.png).

Format lore (derived here, not documented elsewhere): the o2r stores the
reloc blob in N64 big-endian; `tools/reloc_data_symbols.us.txt` offsets are
relative to a 0x50-byte file header, so llFTEmblemSpritesMarioSprite=0x618
puts the first Sprite at 0x668 and the emblems stride 0x660. Each 0x660
unit is [I4 texels 1536][Bitmap 16][Sprite 68][pad], so emblem i's texels
start at 0x58 + i*0x660 — 0x610 BEFORE its Sprite symbol. The texels are
DRAM-swizzled: odd rows have their 4-byte words swapped inside each 8-byte
group. Peak intensity is 9/15 (the CSS watermark translucency the
engine self-calibrates against in ftport port_ui_write_canvas_fit).

Usage: extract_vanilla_emblems.py [--o2r path] [--out website/assets/ui_refs/emblem_ref.png]
"""
import argparse
import os
import zipfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
O2R = os.path.join(HERE, "..", "BattleShip", "build-us", "BattleShip.o2r")
ENTRY = "reloc_fighters_common/FTEmblemSprites"
FIRST, STRIDE = 0x58, 0x660
W, H = 64, 48
NAMES = ["Mario", "Donkey", "Metroid", "Fox", "Kirby",
         "Zelda", "Yoshi", "FZero", "PMonsters", "Mother"]


def emblem(blob, i):
    """One emblem as a bool ink mask."""
    o = FIRST + i * STRIDE
    stride = W // 2
    rows = []
    for y in range(H):
        r = bytearray(blob[o + y * stride:o + y * stride + stride])
        if y % 2:  # undo the DRAM swizzle
            for j in range(0, stride - 7, 8):
                r[j:j + 4], r[j + 4:j + 8] = r[j + 4:j + 8], r[j:j + 4]
        rows.append(bytes(r))
    a = np.frombuffer(b"".join(rows), np.uint8)
    n = np.empty(a.size * 2, np.uint8)
    n[0::2], n[1::2] = a >> 4, a & 0xF
    return n.reshape(H, W) > 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--o2r", default=O2R)
    ap.add_argument("--out", default=os.path.join(
        HERE, "website", "assets", "ui_refs", "emblem_ref.png"))
    ap.add_argument("--scale", type=int, default=4)
    a = ap.parse_args()
    blob = zipfile.ZipFile(a.o2r).read(ENTRY) + b"\0" * (STRIDE * len(NAMES))

    pad, cols = 8, 5
    sheet = Image.new("L", (cols * (W + pad) + pad,
                            2 * (H + pad) + pad), 0)
    for i in range(len(NAMES)):
        m = Image.fromarray((emblem(blob, i) * 255).astype(np.uint8))
        sheet.paste(m, (pad + (i % cols) * (W + pad), pad + (i // cols) * (H + pad)))
    sheet = sheet.resize((sheet.width * a.scale, sheet.height * a.scale), Image.NEAREST)
    sheet.convert("RGB").save(a.out)
    print(f"{a.out}: {len(NAMES)} emblems {W}x{H} I4 -> {sheet.size[0]}x{sheet.size[1]}")


if __name__ == "__main__":
    main()
