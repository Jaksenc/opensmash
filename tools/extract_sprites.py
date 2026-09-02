#!/usr/bin/env python3
"""Extract SSB64 sprites from the BattleShip.o2r reloc files to PNGs.

Usage: extract_sprites.py <reloc_path> <outdir> <name=offset> [name=offset ...]
  e.g. extract_sprites.py reloc_menus/MNPlayersPortraits out mario=0x4728

Offsets are the ll*Sprite values from BattleShip/include/reloc_data.us.h.
The o2r reloc files carry a 0x50-byte OLER header on top of those offsets.
Handles RGBA16/RGBA32/CI4/CI8/IA8/IA16 with the N64 TMEM odd-row XOR-4 fix.
"""
import struct, sys, zipfile, os
from PIL import Image

O2R = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "BattleShip", "build-wasm", "extracted", "BattleShip.o2r")
HDR = 0x50

def rgba5551(px):
    r = (px >> 11) & 0x1F; g = (px >> 6) & 0x1F; b = (px >> 1) & 0x1F; a = px & 1
    return ((r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2), 255 * a)

def deswizzle_addr(addr, row, bpp):
    return addr ^ 4 if (row % 2 == 1 and bpp in (4, 8, 16)) else addr

def load_reloc(reloc, o2r=O2R):
    """Raw bytes of one reloc entry (e.g. 'reloc_menus/MNPlayersPortraits')."""
    with zipfile.ZipFile(o2r) as z:
        return z.read(reloc)


def header_size(data):
    """Byte offset of the reloc payload inside an o2r reloc entry.

    Layout: 0x40 LUS header, u32 file id, u16 intern/extern reloc words,
    u32 extern count, extern_count u16s, u32 data size. Files with no
    externs (all the menu files) come out at HDR=0x50; fighter model files
    carry a few externs and their ll*Sprite offsets shift accordingly.
    """
    extern_count = struct.unpack_from("<I", data, 0x48)[0]
    return 0x4C + extern_count * 2 + 4


def decode_sprite(data, off, name="sprite", storage=False, hdr=None):
    """Decode the Sprite at reloc offset `off` -> PIL RGBA image (or None).

    `off` is the ll*Sprite value from reloc_data.us.h (the 0x50-byte o2r
    header is added here). Prints a diagnostic and returns None when the
    bytes at `off` do not look like a Sprite or use an unhandled format.

    storage=False lays the Bitmap strips out the way libultra draws them
    (logical w x h). storage=True instead returns the texel storage view
    that sprite_codec.decode gives for engine dumps: every strip at its
    full width_img, strips stacked top-to-bottom without overlap.
    hdr=None parses the entry header (see header_size); pass HDR to force
    the plain 0x50 layout.
    """
    if hdr is None:
        hdr = header_size(data)
    off += hdr
    raw = data[off:off + 68]
    x, y, w, h = struct.unpack_from(">4h", raw, 0)
    sx, sy = struct.unpack_from(">2f", raw, 8)
    nbitmaps, _ = struct.unpack_from(">2h", raw, 40)
    bmheight, bmHreal = struct.unpack_from(">2h", raw, 44)
    bmfmt, bmsiz = raw[48], raw[49]
    if not (x == 0 and y == 0 and sx == 1.0 and 0 < w <= 2048 and 0 < h <= 2048):
        print(f"  !! {name}: not a sprite at {off - hdr:#x}")
        return None
    def ptr(o):
        return (struct.unpack_from(">I", data, o)[0] & 0xFFFF) * 4 + hdr
    bitmap_off = ptr(off + 0x34)
    palette_off = ptr(off + 0x20) if bmfmt == 2 else None
    if storage:
        strips = [struct.unpack_from(">4h", data, bitmap_off + i * 16)[1]
                  for i in range(nbitmaps)]
        heights = [struct.unpack_from(">h", data, bitmap_off + i * 16 + 12)[0] or bmHreal
                   for i in range(nbitmaps)]
        w, h = max(strips), sum(heights)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_x = 0
    draw_y = 0
    for i in range(nbitmaps):
        bo = bitmap_off + i * 16
        bw, bw_img, s, t = struct.unpack_from(">4h", data, bo)
        actual_h, lut_off = struct.unpack_from(">2h", data, bo + 12)
        buf = ptr(bo + 8)
        strip_h = actual_h if actual_h > 0 else bmHreal
        if storage:
            bw, s, t = bw_img, 0, 0
            draw_x, draw_y = 0, sum(heights[:i])
        # libultra's sprite renderer lays Bitmap entries left-to-right, then
        # wraps them onto the next bmheight row. `s` and `t` are texture
        # offsets inside each bitmap, not destination coordinates. Portraits
        # are three full-width strips (21, 21, and 3 stored rows) placed at
        # y=0, 20, and 40; the extra row is their shared sampling fringe.
        if draw_x + bw > w:
            draw_x = 0
            draw_y += bmheight
        for row in range(strip_h):
            for col in range(bw):
                source_row = t + row
                source_col = s + col
                if bmfmt == 2 and bmsiz == 0:      # CI4
                    a = deswizzle_addr(source_row * (bw_img // 2) + source_col // 2, source_row, 4)
                    byte = data[buf + a]
                    idx = (byte >> 4) if source_col % 2 == 0 else (byte & 0xF)
                    rgba = rgba5551(struct.unpack_from(">H", data, palette_off + (lut_off + idx) * 2)[0])
                elif bmfmt == 2 and bmsiz == 1:    # CI8
                    a = deswizzle_addr(source_row * bw_img + source_col, source_row, 8)
                    idx = data[buf + a]
                    rgba = rgba5551(struct.unpack_from(">H", data, palette_off + (lut_off + idx) * 2)[0])
                elif bmfmt == 0 and bmsiz == 2:    # RGBA16
                    a = deswizzle_addr((source_row * bw_img + source_col) * 2, source_row, 16)
                    rgba = rgba5551(struct.unpack_from(">H", data, buf + a)[0])
                elif bmfmt == 0 and bmsiz == 3:    # RGBA32
                    a = (source_row * bw_img + source_col) * 4
                    if source_row % 2 == 1: a ^= 8
                    rgba = tuple(data[buf + a:buf + a + 4])
                elif bmfmt == 3 and bmsiz == 1:    # IA8
                    a = deswizzle_addr(source_row * bw_img + source_col, source_row, 8)
                    v = data[buf + a]
                    rgba = ((v >> 4) * 17,) * 3 + ((v & 0xF) * 17,)
                elif bmfmt == 3 and bmsiz == 2:    # IA16
                    a = deswizzle_addr((source_row * bw_img + source_col) * 2, source_row, 16)
                    v = struct.unpack_from(">H", data, buf + a)[0]
                    rgba = (v >> 8,) * 3 + (v & 0xFF,)
                elif bmfmt == 3 and bmsiz == 0:    # IA4 (3 bits intensity + 1 alpha)
                    a = deswizzle_addr(source_row * (bw_img // 2) + source_col // 2, source_row, 4)
                    byte = data[buf + a]
                    v4 = (byte >> 4) if source_col % 2 == 0 else (byte & 0xF)
                    inten = ((v4 >> 1) & 0x7) * 36
                    rgba = (inten, inten, inten, 255 if (v4 & 1) else 0)
                elif bmfmt == 4 and bmsiz == 4:    # I2 (4 pixels/byte, odd-row XOR2)
                    a = source_row * (bw_img // 4) + source_col // 4
                    if source_row % 2 == 1: a ^= 2
                    byte = data[buf + a]
                    shift = (3 - (source_col % 4)) * 2
                    v = ((byte >> shift) & 0x3) * 85
                    rgba = (v, v, v, v)
                elif bmfmt == 4 and bmsiz == 0:    # I4
                    a = deswizzle_addr(source_row * (bw_img // 2) + source_col // 2, source_row, 4)
                    byte = data[buf + a]
                    v = ((byte >> 4) if source_col % 2 == 0 else (byte & 0xF)) * 17
                    rgba = (v, v, v, v)
                else:
                    print(f"  !! {name}: unhandled fmt {bmfmt}/{bmsiz}")
                    return None
                px, py = draw_x + col, draw_y + row
                if 0 <= px < w and 0 <= py < h:
                    img.putpixel((px, py), rgba)
        if not storage:
            draw_x += bw
    img.info["fmt"] = (bmfmt, bmsiz)
    return img


def extract(data, off, name, outdir):
    img = decode_sprite(data, off, name)
    if img is None:
        return None
    out = os.path.join(outdir, f"{name}.png")
    img.save(out)
    print(f"  {name}: {img.width}x{img.height} fmt={img.info['fmt'][0]}/{img.info['fmt'][1]} -> {out}")
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    reloc, outdir = argv[0], argv[1]
    os.makedirs(outdir, exist_ok=True)
    data = load_reloc(reloc)
    for spec in argv[2:]:
        name, off = spec.split("=")
        extract(data, int(off, 16), name, outdir)


if __name__ == "__main__":
    main()
