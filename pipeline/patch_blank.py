#!/usr/bin/env python3
"""Add/remove joint ids in the BLNK (blanked vanilla joints) section of shipped
OSB5 / OSB6 fighter bundles without regenerating the mesh.

    patch_blank.py --fkind 9 --add 13,14 play/*.osb6 play/*-pikachu.osb
    patch_blank.py --fkind 9 --remove 13,14 ...   # exact inverse

OSB6: only the block whose fkind matches is touched (block len is fixed up).
OSB5 (.osb): the whole file is one payload; --fkind is ignored.
Idempotent: joints already present are not duplicated.
"""
import argparse, struct, sys, os

def _osb5_sections_at(d, off=0):
    nj, nv, nt, tw, th = struct.unpack_from("<IIIII", d, off + 4)
    return off + 24 + nj * 4 + tw * th * 2 + nv * 28 + nt * 8

def patch_osb5(d, add, remove):
    if d[:4] != b"OSB5":
        raise ValueError("not OSB5")
    p = d.find(b"BLNK", _osb5_sections_at(d))
    if p < 0:
        raise ValueError("no BLNK section")
    n = struct.unpack_from("<I", d, p + 4)[0]
    ids = list(struct.unpack_from("<%dI" % n, d, p + 8))
    new = [j for j in ids if j not in remove] + [j for j in add if j not in ids]
    if new == ids:
        return d, False
    sec = b"BLNK" + struct.pack("<I", len(new)) + struct.pack("<%dI" % len(new), *new)
    return d[:p] + sec + d[p + 8 + n * 4:], True

def patch_file(path, fkind, add, remove):
    d = open(path, "rb").read()
    if d[:4] == b"OSB5":
        out, ch = patch_osb5(d, add, remove)
    elif d[:4] == b"OSB6":
        tw, th, nt = struct.unpack_from("<III", d, 4)
        off = 16 + tw * th * 2
        parts = [d[:off]]; ch = False
        for _ in range(nt):
            fk, ln = struct.unpack_from("<II", d, off)
            payload = d[off + 8: off + 8 + ln]
            if fk == fkind:
                payload, c = patch_osb5(payload, add, remove); ch |= c
            parts.append(struct.pack("<II", fk, len(payload)) + payload)
            off += 8 + ln
        parts.append(d[off:])
        out = b"".join(parts)
    else:
        raise ValueError("unknown format")
    if ch:
        tmp = path + ".tmp"
        open(tmp, "wb").write(out); os.replace(tmp, path)
    return ch

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fkind", type=int, required=True)
    ap.add_argument("--add", default=""); ap.add_argument("--remove", default="")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()
    add = [int(x) for x in a.add.split(",") if x]
    rem = {int(x) for x in a.remove.split(",") if x}
    n = 0
    for f in a.files:
        try:
            if patch_file(f, a.fkind, add, rem):
                n += 1
        except Exception as e:
            print(f"{f}: SKIP ({e})", file=sys.stderr)
    print(f"patched {n}/{len(a.files)}")
