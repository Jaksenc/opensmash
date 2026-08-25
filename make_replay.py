#!/usr/bin/env python3
"""Author a BattleShip .rpl input replay for the mesh-eval harness.

Writes the SYNetReplay debug file format (netreplay.c): header + metadata +
frame_count * MAXCONTROLLERS SYNetInputFrame records. Both P1 and P2 are
human slots fed the same scripted move tour (P2's stick mirrored in X so the
fighters stay face-to-face). Deterministic: fixed rng_seed, no items.

Timing note: replay input ticks are consumed from VS-scene start. With
BOOT_BATTLE on Hyrule (stage 4, Mario vs Mario) control unlocks at the GO,
input tick ~360. The tour pads to tick 370 then runs the move set.

Usage:
  make_replay.py out.rpl [--stage 4] [--p1 0] [--p2 0]
"""
import argparse
import struct

MAGIC = 0x53534E52
VERSION = 1
MAXCONTROLLERS = 4
SCENE_VSBATTLE = 22

# N64 controller bits (libultra CONT_*)
A = 0x8000
B = 0x4000
Z = 0x2000  # shield in SSB64
START = 0x1000
L, R = 0x0020, 0x0010  # L = taunt, R = grab
CU, CD, CL, CR = 0x0008, 0x0004, 0x0002, 0x0001  # C = jump

GO_TICK = 370  # first tick with control, plus a small safety pad


def seg(frames, buttons=0, x=0, y=0):
    return [(buttons, x, y)] * frames

# Segment schedule (label, frames, buttons, x, y[, mirror]). mirror=True
# flips P2's stick X (used only to bring the fighters together); all other
# segments run UN-mirrored so both fighters face and attack the SAME
# direction — the comparison then sees both models from the same angle.
TOUR = [
    ("pre-go idle",  GO_TICK, 0, 0, 0),
    ("approach",     45, 0, 45, 0, True),  # walk toward center (mirrored)
    ("face",         3, 0, 25, 0),         # both tap RIGHT: same facing
    ("face-settle",  7, 0, 0, 0),
    # walk both directions early: each facing exposes a different side of
    # the mesh (and the turn animation itself).
    ("walk-right",   60, 0, 45, 0),
    ("idle-wr",      25, 0, 0, 0),
    ("walk-left",    75, 0, -45, 0),
    ("idle-wl",      25, 0, 0, 0),
    ("reface",       3, 0, 25, 0),
    ("reface-settle", 12, 0, 0, 0),
    ("idle1",        50, 0, 0, 0),
    ("jab",          3, A, 0, 0),
    ("jab-gap",      37, 0, 0, 0),
    ("jab2",         3, A, 0, 0),
    ("idle2",        47, 0, 0, 0),
    ("ftilt",        20, A, 45, 0),
    ("idle3",        50, 0, 0, 0),
    ("utilt",        20, A, 0, 90),
    ("idle4",        50, 0, 0, 0),
    ("crouch",       40, 0, 0, -90),
    ("idle5",        30, 0, 0, 0),
    ("fsmash",       24, A, 110, 0),
    ("idle6",        56, 0, 0, 0),
    ("usmash",       24, A, 0, 110),
    ("idle7",        56, 0, 0, 0),
    ("hop",          14, 0, 0, 127),
    ("air-idle",     50, 0, 0, 0),
    ("land-idle",    46, 0, 0, 0),
    ("jump2",        14, 0, 0, 127),
    ("nair",         3, A, 0, 0),
    ("air2",         53, 0, 0, 0),
    ("shield",       40, Z, 0, 0),
    ("idle8",        30, 0, 0, 0),
    ("taunt",        3, L, 0, 0),
    ("idle10",       97, 0, 0, 0),
    ("walk-back",    60, 0, -45, 0),
    ("final-idle",   120, 0, 0, 0),
    # fireball LAST: P1's projectile hits P2 and flips its facing, ruining
    # same-facing comparability for later frames — so nothing follows it.
    # P2 shields through it (per-segment override) to avoid knockback.
    ("fireball",     3, B, 0, 0, False, (Z, 0, 0)),
    ("fb-idle",      60, 0, 0, 0, False, (Z, 0, 0)),
]


def build_tour():
    ticks = []
    marks = []
    t = 0
    for entry in TOUR:
        label, n, b, x, y = entry[:5]
        mirror = entry[5] if len(entry) > 5 else False
        p2o = entry[6] if len(entry) > 6 else None
        marks.append((t, label))
        ticks += [(b, x, y, mirror, p2o)] * n
        t += n
    return ticks, marks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--stage", type=int, default=4)    # 4 = Hyrule Castle
    ap.add_argument("--p1", type=int, default=0)       # fkind Mario
    ap.add_argument("--p2", type=int, default=0)
    ap.add_argument("--seed", type=int, default=12345)
    args = ap.parse_args()

    tour, marks = build_tour()
    n = len(tour)
    import json as _json
    _json.dump({"marks": marks, "total": n},
               open(args.out + ".json", "w"))

    md = struct.pack(
        "<10I", MAGIC, VERSION, SCENE_VSBATTLE, 2, args.stage,
        4, 99, 0, 0, args.seed)
    md += struct.pack("<9B", 1, 0x2, 0, 0, 0, 0, 2, 0, 0)
    md += bytes([0, 0, 2, 2])              # player_kinds: HMN,HMN,none,none
    md += bytes([args.p1, args.p2, 0, 0])  # fighter_kinds
    md += bytes([0, 0, 0, 0])              # costumes
    md += bytes([0, 1, 2, 3])              # teams
    md += bytes([9, 9, 9, 9])              # handicaps
    md += bytes([1, 1, 1, 1])              # levels
    md += bytes([0, 0, 0, 0])              # shades
    md += b"\x00" * (80 - len(md))
    assert len(md) == 80, len(md)

    frames = bytearray()
    for tick, (buttons, x, y, mirror, p2o) in enumerate(tour):
        for pl in range(MAXCONTROLLERS):
            if pl == 0:
                frames += struct.pack("<IHbbBBBx", tick, buttons, x, y, 3, 0, 1)
            elif pl == 1:
                if p2o is not None:
                    b2, x2, y2 = p2o
                else:
                    b2, x2, y2 = buttons, (-x if mirror else x), y
                frames += struct.pack("<IHbbBBBx", tick, b2, x2, y2, 3, 0, 1)
            else:
                frames += struct.pack("<IHbbBBBx", tick, 0, 0, 0, 3, 0, 1)

    # FNV-1a input checksum, mirroring syNetInputAccumulateInputChecksum
    # over every (tick, player) frame — lets the game's playback-verify
    # log PASS instead of comparing against 0.
    csum = 2166136261
    for tick, (buttons, x, y, mirror, p2o) in enumerate(tour):
        for pl in range(MAXCONTROLLERS):
            if pl == 0:
                bb, bx, by = buttons, x, y
            elif pl == 1:
                if p2o is not None:
                    bb, bx, by = p2o
                else:
                    bb, bx, by = buttons, (-x if mirror else x), y
            else:
                bb, bx, by = 0, 0, 0
            for val in (pl, tick, bb, bx & 0xFF, by & 0xFF):
                csum ^= val
                csum = (csum * 16777619) & 0xFFFFFFFF

    hdr = struct.pack("<7I", MAGIC, VERSION, 80, 12, n, MAXCONTROLLERS, csum)
    with open(args.out, "wb") as f:
        f.write(hdr)
        f.write(md)
        f.write(frames)

    print(f"replay: {n} ticks ({n/60:.1f}s), stage={args.stage} -> {args.out}")
    for t, label in marks:
        print(f"  tick {t:4d}  {label}")


if __name__ == "__main__":
    main()
