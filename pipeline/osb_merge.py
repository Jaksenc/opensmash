#!/usr/bin/env python3
"""osb_merge.py — pack a character's per-target OSB5 bundles into one OSB6.

Why: every `<slug>-<target>.osb` carries its own copy of the same 1024x1024
RGBA16 atlas (2 MB), so a fully retargeted character is ~27 MB on disk of
which ~26 MB is one texture written thirteen times. OSB6 stores the atlas
once and keeps each target's texture-less OSB5 payload verbatim, keyed by
fighter kind, so the engine can pick the payload for the fighter it is
spawning. Optionally the atlas is downsampled on the way in (512x512 is
visually identical in play and 4x smaller).

Layout (little-endian):
  'OSB6'
  u32 texW, u32 texH, u32 ntargets
  u16 rgba16[texW*texH]            (BE byte pairs, same as OSB5)
  ntargets x {
    u32 fkind, u32 length,
    bytes payload[length]          (an OSB5 file with texW=texH=0 and the
                                    texture bytes removed; everything else,
                                    including trailing sections, verbatim)
  }

The engine (ftport.c port_inject_bundle) reads the shared atlas, seeks to
the payload whose fkind matches the spawning fighter, and hands it to the
unchanged OSB5 loader with the atlas pre-supplied. `--extract` reverses the
packing for the offline tools that still read OSB5.

Usage:
  osb_merge.py play/queen.osb [play/queen-*.osb ...] -o play/queen.osb6 [--atlas 512]
  osb_merge.py play/queen.osb -o play/queen.osb6 --atlas 512      # globs siblings
  osb_merge.py --extract play/queen.osb6 --fkind 1 -o /tmp/queen-fox.osb
  osb_merge.py --info play/queen.osb6
"""
import argparse
import glob
import os
import struct
import sys

FIGHTERS = ["mario", "fox", "donkey", "samus", "luigi", "link",
            "yoshi", "captain", "kirby", "pikachu", "purin", "ness"]
ALIASES = {"dk": "donkey", "donkeykong": "donkey", "jigglypuff": "purin",
           "falcon": "captain", "captainfalcon": "captain"}
HDR = struct.Struct("<5I")


def fkind_for_path(path, base_slug):
    name = os.path.basename(path)[:-len(".osb")]
    if name == base_slug:
        return 0
    if not name.startswith(base_slug + "-"):
        raise SystemExit(f"{path}: not a variant of '{base_slug}'")
    target = name[len(base_slug) + 1:].lower()
    target = ALIASES.get(target, target)
    if target not in FIGHTERS:
        raise SystemExit(f"{path}: unknown target '{target}'")
    return FIGHTERS.index(target)


def split_osb5(data, path):
    if data[:4] != b"OSB5":
        raise SystemExit(f"{path}: not an OSB5 file")
    njoints, nverts, ntris, tw, th = HDR.unpack(data[4:24])
    tex_off = 24 + 4 * njoints
    tex_len = tw * th * 2
    tex = data[tex_off:tex_off + tex_len]
    if len(tex) != tex_len:
        raise SystemExit(f"{path}: truncated texture")
    payload = (b"OSB5" + HDR.pack(njoints, nverts, ntris, 0, 0)
               + data[24:tex_off] + data[tex_off + tex_len:])
    return (tw, th, tex), payload


def join_osb5(payload, tw, th, tex):
    njoints, nverts, ntris, ptw, pth = HDR.unpack(payload[4:24])
    if (ptw, pth) != (0, 0):
        raise SystemExit("payload already carries a texture")
    jo = 24 + 4 * njoints
    return (b"OSB5" + HDR.pack(njoints, nverts, ntris, tw, th)
            + payload[24:jo] + tex + payload[jo:])


VERT = struct.Struct("<fffhhBBBBBBBBbbbB")   # 28 bytes, matches OSB5Vert
assert VERT.size == 28


def rescale_uvs(payload, scale, size):
    """Return a copy of a texture-less OSB5 payload with vertex s,t scaled
    to a `size` x `size` atlas."""
    njoints, nverts, ntris, _, _ = HDR.unpack(payload[4:24])
    vo = 24 + 4 * njoints
    out = bytearray(payload)
    limit = size * 32 - 1
    for i in range(nverts):
        at = vo + i * VERT.size
        s, t = struct.unpack_from("<hh", out, at + 12)
        s = max(0, min(limit, int(round(s * scale))))
        t = max(0, min(limit, int(round(t * scale))))
        struct.pack_into("<hh", out, at + 12, s, t)
    return bytes(out)


# ---- RGBA16 <-> RGBA8 -------------------------------------------------------

def decode_rgba16(tex, tw, th):
    import numpy as np
    a = np.frombuffer(tex, dtype=">u2").reshape(th, tw)
    r = ((a >> 11) & 31).astype(np.uint16)
    g = ((a >> 6) & 31).astype(np.uint16)
    b = ((a >> 1) & 31).astype(np.uint16)
    al = (a & 1).astype(np.uint8) * 255
    # 5-bit -> 8-bit with bit replication (exact inverse of >>3 for the
    # values the writer can produce)
    rgb = np.dstack([(r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2)]).astype(np.uint8)
    return np.dstack([rgb, al])


def pack_rgba16_dithered(rgba8):
    """Exact copy of convert_rigged.pack_rgba16_dithered (that module runs
    argv parsing at import time, so it cannot be imported here). RGBA8
    (H,W,4) -> RGBA16 5551 BE with a luma-gated 4x4 Bayer dither."""
    import numpy as np
    a = np.asarray(rgba8, np.float32)
    BAYER = (np.array([[0, 8, 2, 10], [12, 4, 14, 6],
                       [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) / 16.0 - 0.46875) * 8.0
    H, W = a.shape[:2]
    doff = np.tile(BAYER, (H // 4 + 1, W // 4 + 1))[:H, :W]
    doff = doff * float(os.environ.get("OSB_DITHER", "1"))
    luma = a[..., :3].max(2)
    gate = np.clip((luma - 48.0) / 48.0, 0.0, 1.0)
    rgb = np.clip(a[..., :3] + (doff * gate)[..., None], 0, 255).astype(np.uint16) >> 3
    alpha = (a[..., 3] >= 128).astype(np.uint16)
    p16 = (rgb[..., 0] << 11) | (rgb[..., 1] << 6) | (rgb[..., 2] << 1) | alpha
    return p16.astype(">u2").tobytes()


def source_atlas_for(base_path):
    """play/<slug>.osb -> play/ui/<slug>/bundle-atlas.png if present."""
    slug = os.path.basename(base_path)[:-4]
    candidate = os.path.join(os.path.dirname(os.path.abspath(base_path)), "ui", slug, "bundle-atlas.png")
    return candidate if os.path.exists(candidate) else None


def resample_atlas(tex, tw, th, size, source=None):
    """Return (rgba16 bytes, w, h) for a size x size atlas.

    Preferred path: resize the 8-bit source atlas the writer packed from and
    dither once with the writer's routine, so the result is exactly what
    convert_rigged would have emitted for a size x size atlas. Fallback (no
    source on disk): decode the 5-bit texture, resize, and dither that.
    """
    from PIL import Image
    import numpy as np
    if source is not None:
        im = Image.open(source).convert("RGBA")
        if im.size != (tw, th):
            raise SystemExit(f"{source}: {im.size} does not match the bundle atlas {tw}x{th}")
        if pack_rgba16_dithered(np.asarray(im)) != tex:
            raise SystemExit(f"{source}: does not reproduce the bundle's texture; refusing to resample from it")
        small = im.resize((size, size), Image.LANCZOS)
        return pack_rgba16_dithered(np.asarray(small)), size, size
    rgba = decode_rgba16(tex, tw, th)
    im = Image.fromarray(rgba, "RGBA").resize((size, size), Image.LANCZOS)
    out = np.asarray(im).copy()
    out[..., 3] = np.where(out[..., 3] > 127, 255, 0)
    return pack_rgba16_dithered(out), size, size


# ---- commands ---------------------------------------------------------------

def cmd_merge(args):
    inputs = list(args.inputs)
    base = inputs[0]
    if not base.endswith(".osb"):
        raise SystemExit("first input must be the base <slug>.osb")
    base_slug = os.path.basename(base)[:-4]
    if "-" in base_slug:
        raise SystemExit(f"base file must be the mario bundle, got '{base_slug}'")
    if len(inputs) == 1:
        inputs += sorted(glob.glob(os.path.join(os.path.dirname(base) or ".", f"{base_slug}-*.osb")))

    shared = None
    targets = {}
    for path in inputs:
        data = open(path, "rb").read()
        fk = fkind_for_path(path, base_slug)
        (tw, th, tex), payload = split_osb5(data, path)
        if shared is None:
            shared = (tw, th, tex)
        elif shared[2] != tex:
            raise SystemExit(f"{path}: atlas differs from {base}; cannot share")
        if fk in targets:
            # e.g. both queen-dk.osb and queen-donkey.osb: keep the first
            print(f"  skip {os.path.basename(path)} (fkind {fk} already from "
                  f"{os.path.basename(targets[fk][0])})")
            continue
        targets[fk] = (path, payload)

    tw, th, tex = shared
    if args.atlas and args.atlas != tw:
        # Vertex s,t are absolute texel coordinates in 1/32 texel units
        # (the writer emits u * texW * 32), so a resampled atlas needs every
        # payload's UVs rescaled to match or the texture reads scrambled.
        scale = args.atlas / tw
        targets = {fk: (path, rescale_uvs(payload, scale, args.atlas))
                   for fk, (path, payload) in targets.items()}
        source = args.source_atlas or source_atlas_for(base)
        print(f"  atlas {tw}x{th} -> {args.atlas}x{args.atlas} from "
              f"{'source ' + os.path.relpath(source) if source else 'the packed RGBA16 (no source atlas found)'}")
        tex, tw, th = resample_atlas(tex, tw, th, args.atlas, source)

    with open(args.output, "wb") as f:
        f.write(b"OSB6")
        f.write(struct.pack("<III", tw, th, len(targets)))
        f.write(tex)
        for fk in sorted(targets):
            path, payload = targets[fk]
            f.write(struct.pack("<II", fk, len(payload)))
            f.write(payload)
    total_in = sum(os.path.getsize(p) for p, _ in targets.values())
    out = os.path.getsize(args.output)
    print(f"{args.output}: {len(targets)} targets "
          f"[{', '.join(FIGHTERS[k] for k in sorted(targets))}], atlas {tw}x{th}; "
          f"{total_in / 1048576:.1f} MB in -> {out / 1048576:.2f} MB out")


def read_osb6(path):
    data = open(path, "rb").read()
    if data[:4] != b"OSB6":
        raise SystemExit(f"{path}: not an OSB6 file")
    tw, th, n = struct.unpack("<III", data[4:16])
    o = 16
    tex = data[o:o + tw * th * 2]
    o += tw * th * 2
    targets = {}
    for _ in range(n):
        fk, length = struct.unpack("<II", data[o:o + 8])
        o += 8
        targets[fk] = data[o:o + length]
        o += length
    return tw, th, tex, targets


def cmd_extract(args):
    tw, th, tex, targets = read_osb6(args.extract)
    if args.fkind not in targets:
        raise SystemExit(f"no target fkind {args.fkind} in {args.extract} "
                         f"(have {sorted(targets)})")
    open(args.output, "wb").write(join_osb5(targets[args.fkind], tw, th, tex))
    print(f"{args.output}: OSB5 for {FIGHTERS[args.fkind]} at {tw}x{th}")


def cmd_info(args):
    tw, th, tex, targets = read_osb6(args.info)
    print(f"{args.info}: atlas {tw}x{th} ({len(tex) / 1024:.0f} KB), {len(targets)} targets")
    for fk in sorted(targets):
        p = targets[fk]
        nj, nv, nt, _, _ = HDR.unpack(p[4:24])
        print(f"  fkind {fk:2d} {FIGHTERS[fk]:8s} {len(p) / 1024:6.1f} KB  "
              f"joints {nj} verts {nv} tris {nt}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("inputs", nargs="*", help="base <slug>.osb then variants (or just the base)")
    ap.add_argument("-o", "--output")
    ap.add_argument("--atlas", type=int, default=None, help="downsample the atlas to NxN (e.g. 512)")
    ap.add_argument("--source-atlas", default=None,
                    help="8-bit atlas PNG to resample from (default: play/ui/<slug>/bundle-atlas.png)")
    ap.add_argument("--extract", metavar="OSB6", help="write one target back out as OSB5")
    ap.add_argument("--fkind", type=int, default=0, help="target for --extract")
    ap.add_argument("--info", metavar="OSB6")
    args = ap.parse_args()
    if args.info:
        return cmd_info(args)
    if args.extract:
        if not args.output:
            ap.error("--extract needs -o")
        return cmd_extract(args)
    if not args.inputs or not args.output:
        ap.error("merge needs inputs and -o")
    return cmd_merge(args)


if __name__ == "__main__":
    sys.exit(main())
