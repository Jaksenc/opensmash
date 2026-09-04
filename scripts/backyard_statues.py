#!/usr/bin/env python3
"""Backyard statue bundles — real .osb6 files, zero Tripo, zero ROM.

Builds one single-target OSB5 payload per starter-12 fighter and packs it
as play/<slug>.osb6 in the exact layout pipeline/osb_merge.py + the
convert_rigged.py binary5 writer produce (same magic, header, vertex stride,
RGBA16 BE texture, BIND/BLNK sections), with:

  * joints = [0], every vertex weighted 100% to joint 0, BIND = identity.
    I.e. a rigid "statue" in rest pose — it renders correctly anywhere an
    OSB5/OSB6 is drawn (the repo's own three.js preview, OgStudio, the
    engine's OSB5 loader path) but it will NOT dance: real per-joint
    skinning needs the ROM-derived skeletons (skels/*.skel) and a Tripo
    rig, which is what pipeline/run_character.py is for.
  * mesh = procedural chibi humanoid (~170 tris, N64-budget) textured from
    the fighter's own backyard art: face from the thumb, outfit/pants/skin
    sampled medians as flat atlas cells.
  * frame = Y-up, facing +X (matches the converter's facing convention).

Verification (no engine needed): web-prototype/shared/backyard-statues.test.js
parses every play/<slug>.osb6 with the repo's own parseOsb6Preview and
asserts finite positions, sane bbox, and in-range indices.

Upgrade path: run pipeline/run_character.py with TRIPO_API_KEY + ROM to
replace these with fully rigged bundles (same file names).

Usage: .venv/bin/python scripts/backyard_statues.py [--slug X] [--force]
"""
import argparse
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(HERE, "web-prototype", "config", "backyard-starter.json")
REFS = os.path.join(HERE, "backyard", "refs")
FIGHTERS = ["mario", "fox", "donkey", "samus", "luigi", "link",
            "yoshi", "captain", "kirby", "pikachu", "purin", "ness"]
TW = TH = 512


def ref_for(handle):
    for kind in ("thumb", "action", "sprite"):
        p = os.path.join(REFS, f"{handle}_{kind}.webp")
        if os.path.exists(p):
            return p
    return None


def sample_palette(ref):
    from PIL import Image
    import numpy as np
    im = Image.open(ref).convert("RGB")
    w, h = im.size
    a = np.asarray(im).reshape(-1, 3)
    corner = np.asarray(im.crop((0, 0, 8, 8))).reshape(-1, 3).mean(axis=0)
    mask = (np.abs(a.astype(int) - corner.astype(int)).sum(axis=1) > 90)
    fig = a[mask] if mask.sum() > 100 else a
    n = len(fig)
    face = tuple(int(v) for v in np.median(fig[:n // 3].reshape(-1, 3), axis=0))
    outfit = tuple(int(v) for v in np.median(fig[n // 3:2 * n // 3].reshape(-1, 3), axis=0))
    pants = tuple(int(v) for v in np.median(fig[2 * n // 3:].reshape(-1, 3), axis=0))
    return face, outfit, pants


class Builder:
    def __init__(self):
        self.verts = []  # (x,y,z, uvd_u,uvd_v, nx,ny,nz)
        self.tris = []

    def box(self, cx, cy, cz, sx, sy, sz, uv):
        """Axis box. uv = dict face->(u0,v0,u1,v1) in 0..1, faces ordered
        +X,-X,+Y,-Y,+Z,-Z; missing faces reuse '+X'. Facing is +X."""
        x0, x1, y0, y1, z0, z1 = cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2, cz - sz / 2, cz + sz / 2
        corners = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                   (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        faces = [
            ((1, 2, 6, 5), (1, 0, 0)), ((0, 4, 7, 3), (-1, 0, 0)),
            ((3, 7, 6, 2), (0, 1, 0)), ((0, 1, 5, 4), (0, -1, 0)),
            ((4, 5, 6, 7), (0, 0, 1)), ((0, 3, 2, 1), (0, 0, -1)),
        ]
        names = ["+X", "-X", "+Y", "-Y", "+Z", "-Z"]
        for name, ((i0, i1, i2, i3), n) in zip(names, faces):
            r = uv.get(name, uv["+X"])
            u0, v0, u1, v1 = r
            quad = [(i0, u0, v1), (i1, u1, v1), (i2, u1, v0), (i3, u0, v0)]
            b = len(self.verts)
            for ci, u, v in quad:
                x, y, z = corners[ci]
                self.verts.append((x, y, z, u, v, *n))
            self.tris += [(b, b + 1, b + 2),
                          (b, b + 2, b + 3)]

    @staticmethod
    def _cell(u, v, w=64, h=64):
        # inclusive texel ranges, mapped to texel centers so quad corners
        # never sample the neighbouring (background) texel
        return ((u + 0.5) / TW, (v + 0.5) / TH,
                (u + w - 0.5) / TW, (v + h - 0.5) / TH)


def build_mesh(face_uv, flat):
    """flat = dict of color-cell rects. Returns (verts, tris)."""
    b = Builder()
    skin, outfit, pants, shoe = flat["skin"], flat["outfit"], flat["pants"], flat["shoe"]
    # legs (feet y=0)
    for s in (-1, 1):
        b.box(s * 0.13, 0.45, 0, 0.17, 0.9, 0.19, {"+X": pants})
        b.box(s * 0.13, 0.08, 0.03, 0.18, 0.16, 0.26, {"+X": shoe})
    # torso
    b.box(0, 1.25, 0, 0.55, 0.65, 0.32, {"+X": outfit})
    # arms, slight A-pose
    for s in (-1, 1):
        b.box(s * 0.42, 1.32, 0, 0.34, 0.15, 0.16, {"+X": outfit})
        b.box(s * 0.62, 1.22, 0, 0.13, 0.13, 0.14, {"+X": skin})
    # head (0.44 cube, face art on +X)
    b.box(0, 1.82, 0, 0.44, 0.44, 0.44,
          {"+X": face_uv, "-X": skin, "+Y": skin, "-Y": skin, "+Z": skin, "-Z": skin})
    # cap brim nod (most backyard kids wear caps)
    b.box(0.24, 1.98, 0, 0.22, 0.06, 0.4, {"+X": outfit})
    return b.verts, b.tris


def pack_rgba16(im):
    px = im.convert("RGBA").load()
    out = bytearray()
    for y in range(im.height):
        for x in range(im.width):
            r, g, bl, a = px[x, y]
            out += struct.pack(">H", ((r >> 3) << 11) | ((g >> 3) << 6) | ((bl >> 3) << 1) | (1 if a >= 128 else 0))
    return bytes(out)


def build_osb6(entry):
    from PIL import Image
    slug = entry["slug"]
    ref = ref_for(entry["handle"])
    if not ref:
        raise RuntimeError(f"no ref art for {entry['handle']}")
    face, outfit, pants = sample_palette(ref)

    atlas = Image.new("RGBA", (TW, TH), (255, 0, 255, 255))
    # Face comes from the square portrait (its center is the face), falling
    # back to the raw ref. The thumb's top square is mostly backdrop.
    portrait = os.path.join(HERE, "play", "ui", slug, "portrait_raw.png")
    fsrc = Image.open(portrait).convert("RGB") if os.path.exists(portrait) else None
    if fsrc is None:
        thumb = Image.open(ref).convert("RGB")
        side = min(thumb.size)
        fsrc = thumb.crop(((thumb.width - side) // 2, (thumb.height - side) // 2,
                           (thumb.width + side) // 2, (thumb.height + side) // 2)).resize((512, 512), Image.LANCZOS)
    face_im = fsrc.crop((128, 110, 384, 366)).resize((256, 256), Image.LANCZOS)
    atlas.paste(face_im, (128, 8))
    cells = {}
    for name, color, pos in (("skin", face, (0, 300)), ("outfit", outfit, (80, 300)),
                             ("pants", pants, (160, 300)), ("shoe", (40, 32, 28), (240, 300))):
        for dx in range(64):
            for dy in range(64):
                atlas.putpixel((pos[0] + dx, pos[1] + dy), color + (255,))
        cells[name] = Builder._cell(*pos)
    face_uv = ((128 + 0.5) / TW, (8 + 0.5) / TH,
               (128 + 256 - 0.5) / TW, (8 + 256 - 0.5) / TH)

    verts, tris = build_mesh(face_uv, cells)
    fkind = FIGHTERS.index(entry["base"])
    payload = bytearray(b"OSB5")
    payload += struct.pack("<IIIII", 1, len(verts), len(tris), 0, 0)
    payload += struct.pack("<I", 0)  # joint table: single root
    for x, y, z, u, v, nx, ny, nz in verts:
        s = max(0, min(TW * 32 - 1, int(round(u * TW * 32))))
        t = max(0, min(TH * 32 - 1, int(round(v * TH * 32))))
        payload += struct.pack("<fffhh", x, y, z, s, t)
        payload += struct.pack("<BBBB", 0, 0, 0, 0)
        payload += struct.pack("<BBBB", 255, 0, 0, 0)
        payload += struct.pack("<bbbB", max(-127, min(127, int(nx * 127))),
                               max(-127, min(127, int(ny * 127))),
                               max(-127, min(127, int(nz * 127))), 0)
    for t3 in tris:
        payload += struct.pack("<HHHH", t3[0], t3[1], t3[2], 0)
    payload += b"BIND" + struct.pack("<fff", 0, 0, 0)
    for r in range(3):
        payload += struct.pack("<fff", *[(1.0 if i == r else 0.0) for i in range(3)])
    payload += b"BLNK" + struct.pack("<II", 1, 0)

    tex = pack_rgba16(atlas)
    osb6 = bytearray(b"OSB6") + struct.pack("<III", TW, TH, 1) + tex
    osb6 += struct.pack("<II", fkind, len(payload)) + payload
    out = os.path.join(HERE, "play", f"{slug}.osb6")
    if os.path.exists(out):
        os.remove(out)
    with open(out, "wb") as f:
        f.write(osb6)
    print(f"statue {slug} <- {entry['handle']} ({entry['base']} fkind {fkind}): "
          f"{len(verts)} verts, {len(tris)} tris, {len(osb6)//1024} KB")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", help="only this starter slug")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    entries = json.load(open(CONFIG))
    if args.slug:
        entries = [e for e in entries if e["slug"] == args.slug]
        if not entries:
            sys.exit(f"unknown slug {args.slug}")
    for e in entries:
        out = os.path.join(HERE, "play", f"{e['slug']}.osb6")
        if os.path.exists(out) and not args.force:
            print(f"skip {e['slug']} (exists)")
            continue
        build_osb6(e)


if __name__ == "__main__":
    main()
