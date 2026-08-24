#!/usr/bin/env python3
"""Decode/encode SSB64 sprite dumps (the .json/.bufs/.tlut files written by
port_ui_dump_sprite) to/from PIL images. DRAM state = blanket u32 byte
reversal + TMEM odd-row swizzle (group 16B for 32bpp, 8B otherwise)."""
import json
import os

from PIL import Image


def u32rev(b):
    out = bytearray(len(b))
    for i in range(0, len(b) - 3, 4):
        out[i:i + 4] = b[i:i + 4][::-1]
    return bytes(out)


def swizzle(data, w, h, bpt, grp=None):
    if grp is None:
        grp = 16 if bpt == 32 else 8
    row = w * bpt // 8
    out = bytearray(data)
    for y in range(1, h, 2):
        base = y * row
        half = grp // 2
        for q in range(0, row - (grp - 1), grp):
            i = base + q
            out[i:i + half], out[i + half:i + grp] = out[i + half:i + grp], out[i:i + half]
    return bytes(out)


def _rgba5551(v):
    r, g, b, a = (v >> 11) & 31, (v >> 6) & 31, (v >> 1) & 31, v & 1
    return (r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2, 255 if a else 0)


def decode(prefix):
    """prefix.json[.bin] etc -> (PIL RGBA image, meta)."""
    def find(ext):
        for cand in (f"{prefix}.{ext}", f"{prefix}.{ext}.bin"):
            if os.path.exists(cand):
                return cand
        return None
    meta = json.load(open(find("json")))
    raw = u32rev(open(find("bufs"), "rb").read())
    tlut = None
    tf = find("tlut")
    if tf:
        t = u32rev(open(tf, "rb").read())
        tlut = [(t[i] << 8) | t[i + 1] for i in range(0, len(t), 2)]
    bpt = {0: 4, 1: 8, 2: 16, 3: 32}[meta["bmsiz"]]
    W = max(b["width_img"] for b in meta["bitmaps"])
    H = sum(b["actual_h"] for b in meta["bitmaps"])
    im = Image.new("RGBA", (W, H))
    off = 0
    yy = 0
    for b in meta["bitmaps"]:
        w, h = b["width_img"], b["actual_h"]
        n = w * h * bpt // 8
        seg = swizzle(raw[off:off + n], w, h, bpt)
        for y in range(h):
            for x in range(w):
                if bpt == 32:
                    i = (y * w + x) * 4
                    px = (seg[i], seg[i + 1], seg[i + 2], seg[i + 3])
                elif bpt == 16:
                    i = (y * w + x) * 2
                    px = _rgba5551((seg[i] << 8) | seg[i + 1])
                elif bpt == 8:
                    v = seg[y * w + x]
                    if meta["bmfmt"] == 3:  # IA8
                        it = (v >> 4) * 17
                        px = (it, it, it, (v & 0xF) * 17)
                    else:
                        px = _rgba5551(tlut[b["lut_off"] + v]) if tlut else (v, v, v, 255)
                else:
                    v = seg[(y * w + x) // 2]
                    idx = (v & 0xF) if (x & 1) else (v >> 4)
                    px = _rgba5551(tlut[b["lut_off"] + idx]) if tlut else (idx * 17,) * 3 + (255,)
                im.putpixel((x, yy + y), px)
        off += n
        yy += h
    return im, meta


def encode(logical_bytes, w, h, bpt):
    """logical texel bytes -> DRAM state (swizzle then u32 reversal)."""
    return u32rev(swizzle(logical_bytes, w, h, bpt))
