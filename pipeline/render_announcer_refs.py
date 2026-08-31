#!/usr/bin/env python3
"""Render SSB64 announcer references at their in-game pitch.

The sounds2 bank stores source ADPCM waves at a nominal 44.1 kHz, but FGM
programs do not play those waves at unity pitch.  The game mixes at 32 kHz
and applies a cents offset from both the FGM table and its calling bytecode.
Dumping the decoded source samples directly as 44.1 kHz WAVs therefore makes
most announcer lines much too fast and high.

This script follows the US ROM's FGM ucode -> FGM table -> sounds2 sample
mapping, decodes VADPCM, and applies the same quantized 4-tap resampler used
by the port's N64 audio mixer.  It writes individual clips, two conditioning
montages, and a manifest describing the resolved playback parameters.
"""

import argparse
import json
import math
import os
import struct
import sys
import wave

try:
    from .dump_fgm_bank import Ctl, SEGMENTS, clamp16, decode_raw16, decode_vadpcm
except ImportError:  # direct execution: python3 pipeline/render_announcer_refs.py
    from dump_fgm_bank import Ctl, SEGMENTS, clamp16, decode_raw16, decode_vadpcm


OUTPUT_RATE = 32000
FGM_TABLE = (0xF57BF0, 0x2DD0)
FGM_UCODE = (0xF5A9C0, 0x4B20)

# US-region enum values from decomp/src/gm/gmsound.h.  The renderer resolves
# the sample and pitch from ROM bytecode; these IDs only choose each line.
NAME_LINES = [
    ("mario", "Mario", 499),
    ("donkey_kong", "Donkey Kong", 483),
    ("samus", "Samus", 513),
    ("fox", "Fox", 486),
    ("yoshi", "Yoshi", 535),
    ("link", "Link", 497),
    ("pikachu", "Pikachu", 507),
    ("kirby", "Kirby", 496),
    ("luigi", "Luigi", 498),
    ("ness", "Ness", 501),
    ("captain_falcon", "Captain Falcon", 485),
    ("jigglypuff", "Jigglypuff", 508),
]

PHRASE_LINES = [
    ("free_for_all", "Free for all", 512),
    ("choose_your_character", "Choose your character", 479),
    ("this_games_winner_is", "This game's winner is", 534),
    ("wins", "Wins", 533),
    ("race_to_the_finish", "Race to the finish", 495),
    ("congratulations", "Congratulations", 465),
]

# port/audio/mixer.c::resample_table, interpreted as signed int16.
RESAMPLE_TABLE = (
    (0x0C39, 0x66AD, 0x0D46, -0x21), (0x0B39, 0x6696, 0x0E5F, -0x28),
    (0x0A44, 0x6669, 0x0F83, -0x30), (0x095A, 0x6626, 0x10B4, -0x38),
    (0x087D, 0x65CD, 0x11F0, -0x41), (0x07AB, 0x655E, 0x1338, -0x4A),
    (0x06E4, 0x64D9, 0x148C, -0x54), (0x0628, 0x643F, 0x15EB, -0x5F),
    (0x0577, 0x638F, 0x1756, -0x6A), (0x04D1, 0x62CB, 0x18CB, -0x76),
    (0x0435, 0x61F3, 0x1A4C, -0x82), (0x03A4, 0x6106, 0x1BD7, -0x8F),
    (0x031C, 0x6007, 0x1D6C, -0x9C), (0x029F, 0x5EF5, 0x1F0B, -0xAA),
    (0x022A, 0x5DD0, 0x20B3, -0xB8), (0x01BE, 0x5C9A, 0x2264, -0xC6),
    (0x015B, 0x5B53, 0x241E, -0xD4), (0x0101, 0x59FC, 0x25E0, -0xE2),
    (0x00AE, 0x5896, 0x27A9, -0xF0), (0x0063, 0x5720, 0x297A, -0xFE),
    (0x001F, 0x559D, 0x2B50, -0x10C), (-0x1E, 0x540D, 0x2D2C, -0x118),
    (-0x54, 0x5270, 0x2F0D, -0x125), (-0x84, 0x50C7, 0x30F3, -0x130),
    (-0xAD, 0x4F14, 0x32DC, -0x13A), (-0xD2, 0x4D57, 0x34C8, -0x143),
    (-0xF1, 0x4B91, 0x36B6, -0x14A), (-0x10B, 0x49C2, 0x38A5, -0x150),
    (-0x121, 0x47ED, 0x3A95, -0x154), (-0x132, 0x4611, 0x3C85, -0x155),
    (-0x140, 0x4430, 0x3E74, -0x154), (-0x14A, 0x424A, 0x4060, -0x151),
    (-0x151, 0x4060, 0x424A, -0x14A), (-0x154, 0x3E74, 0x4430, -0x140),
    (-0x155, 0x3C85, 0x4611, -0x132), (-0x154, 0x3A95, 0x47ED, -0x121),
    (-0x150, 0x38A5, 0x49C2, -0x10B), (-0x14A, 0x36B6, 0x4B91, -0xF1),
    (-0x143, 0x34C8, 0x4D57, -0xD2), (-0x13A, 0x32DC, 0x4F14, -0xAD),
    (-0x130, 0x30F3, 0x50C7, -0x84), (-0x125, 0x2F0D, 0x5270, -0x54),
    (-0x118, 0x2D2C, 0x540D, -0x1E), (-0x10C, 0x2B50, 0x559D, 0x001F),
    (-0xFE, 0x297A, 0x5720, 0x0063), (-0xF0, 0x27A9, 0x5896, 0x00AE),
    (-0xE2, 0x25E0, 0x59FC, 0x0101), (-0xD4, 0x241E, 0x5B53, 0x015B),
    (-0xC6, 0x2264, 0x5C9A, 0x01BE), (-0xB8, 0x20B3, 0x5DD0, 0x022A),
    (-0xAA, 0x1F0B, 0x5EF5, 0x029F), (-0x9C, 0x1D6C, 0x6007, 0x031C),
    (-0x8F, 0x1BD7, 0x6106, 0x03A4), (-0x82, 0x1A4C, 0x61F3, 0x0435),
    (-0x76, 0x18CB, 0x62CB, 0x04D1), (-0x6A, 0x1756, 0x638F, 0x0577),
    (-0x5F, 0x15EB, 0x643F, 0x0628), (-0x54, 0x148C, 0x64D9, 0x06E4),
    (-0x4A, 0x1338, 0x655E, 0x07AB), (-0x41, 0x11F0, 0x65CD, 0x087D),
    (-0x38, 0x10B4, 0x6626, 0x095A), (-0x30, 0x0F83, 0x6669, 0x0A44),
    (-0x28, 0x0E5F, 0x6696, 0x0B39), (-0x21, 0x0D46, 0x66AD, 0x0C39),
)


def package_entries(blob):
    count = struct.unpack_from(">I", blob, 0)[0]
    offsets = list(struct.unpack_from(">%dI" % count, blob, 4))
    offsets.append(len(blob))
    return [blob[offsets[i]:offsets[i + 1]] for i in range(count)]


def read_u15(data, pos):
    value = data[pos]
    pos += 1
    if value & 0x80:
        value = ((value & 0x7F) << 8) | data[pos]
        pos += 1
    return value, pos


def resolve_ucode(entry):
    """Return (FGM table ID, note cents) for the first played note."""
    pos = 0
    table_id = None
    pitch_prefix = 0
    while pos < len(entry):
        instr = entry[pos]
        pos += 1
        if (instr & 0xF8) >= 0xD0:
            if instr == 0xD0:
                break
            if instr in (0xD1, 0xD9):
                value, pos = read_u15(entry, pos)
                if instr == 0xD1:
                    table_id = value
            elif instr == 0xD4:
                for _ in range(6):
                    _, pos = read_u15(entry, pos)
            elif instr in (0xD2, 0xD3, 0xD5, 0xD6, 0xD7, 0xD8,
                           0xDC, 0xDD, 0xDE):
                pos += 1
            elif instr == 0xDF:
                pitch_prefix = -0x960
            elif instr == 0xE0:
                pitch_prefix = -0x12C0
            continue

        timer = instr & 7
        if timer == 7:
            _, pos = read_u15(entry, pos)
        if instr & 0xF8:
            if table_id is None:
                raise ValueError("note precedes D1 table selection")
            note_cents = ((instr >> 3) * 100) - 1300 + pitch_prefix
            return table_id, note_cents
    raise ValueError("FGM ucode entry has no played note")


def resolve_table(entry):
    """Return (sounds2 sample ID, table cents) from an FGM table program."""
    pos = 0
    sample_id = None
    cents = 0
    while pos < len(entry):
        instr = entry[pos]
        pos += 1
        timer = instr & 0xF
        if timer & 8:
            first = entry[pos]
            pos += 1
            if first & 0x80:
                pos += 1
        opcode = instr & 0xF0
        if opcode in (0x00, 0x10, 0x30, 0x50):
            pos += 1
        elif opcode == 0x20:
            cents = struct.unpack_from(">h", entry, pos)[0]
            pos += 2
        elif opcode == 0x40:
            pos += 1
            _, pos = read_u15(entry, pos)
        elif opcode == 0x60:
            sample_id, pos = read_u15(entry, pos)
        elif opcode == 0x70:
            break
        elif opcode in (0x80, 0x90):
            pass
        else:
            raise ValueError("unknown FGM table opcode 0x%02x" % opcode)
    if sample_id is None:
        raise ValueError("FGM table entry has no sample selection")
    return sample_id, cents


def n64_resample(samples, ratio):
    """Apply mixer.c's quantized 4-tap resampler to one complete waveform."""
    pitch = int(ratio * 0x8000)
    step = pitch << 1
    out_count = int(math.ceil(len(samples) * 0x10000 / step)) + 4
    source = [0, 0, 0, 0] + list(samples) + [0] * 12
    index = 0
    phase = 0
    out = []
    for _ in range(out_count):
        coeffs = RESAMPLE_TABLE[(phase * 64) >> 16]
        value = sum(source[index + j] * coeffs[j] for j in range(4)) >> 15
        out.append(clamp16(value))
        phase += step
        index += phase >> 16
        phase &= 0xFFFF
    # Preserve the mixer tail but remove exact zero padding after it.
    while out and out[-1] == 0:
        out.pop()
    return out, pitch


def write_wav(path, samples, rate=OUTPUT_RATE):
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(struct.pack("<%dh" % len(samples), *samples))


def montage(clips, gap_ms=120):
    gap = [0] * round(OUTPUT_RATE * gap_ms / 1000)
    out = []
    for i, clip in enumerate(clips):
        if i:
            out.extend(gap)
        out.extend(clip)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("outdir")
    parser.add_argument("--rom", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "BattleShip",
        "baserom.us.z64"))
    args = parser.parse_args()

    with open(args.rom, "rb") as src:
        rom = src.read()

    ctl_off, ctl_size = SEGMENTS["sounds2"]["ctl"]
    tbl_off, tbl_size = SEGMENTS["sounds2"]["tbl"]
    ctl = Ctl(rom[ctl_off:ctl_off + ctl_size], rom[tbl_off:tbl_off + tbl_size])
    bank = ctl.parse()["banks"][0]
    sounds = bank["instruments"][0]["sounds"]
    sample_data = rom[tbl_off:tbl_off + tbl_size]

    fgm_table = package_entries(rom[FGM_TABLE[0]:FGM_TABLE[0] + FGM_TABLE[1]])
    fgm_ucode = package_entries(rom[FGM_UCODE[0]:FGM_UCODE[0] + FGM_UCODE[1]])

    os.makedirs(args.outdir, exist_ok=True)
    individual = os.path.join(args.outdir, "individual")
    os.makedirs(individual, exist_ok=True)

    rendered = {}
    manifest = []
    for group, lines in (("name", NAME_LINES), ("phrase", PHRASE_LINES)):
        for slug, text, fgm_id in lines:
            table_id, note_cents = resolve_ucode(fgm_ucode[fgm_id])
            sample_id, table_cents = resolve_table(fgm_table[table_id])
            total_cents = table_cents + note_cents
            ratio = 2.0 ** (total_cents / 1200.0)

            sound = sounds[sample_id]
            wavetable = sound["wavetable"]
            raw = sample_data[wavetable["base"]:wavetable["base"] + wavetable["len"]]
            if wavetable["type"] == 0:
                pcm = decode_vadpcm(raw, wavetable["book"], wavetable["order"],
                                    wavetable["npredictors"])
            else:
                pcm = decode_raw16(raw)
            output, quantized_pitch = n64_resample(pcm, ratio)
            path = os.path.join(individual, slug + ".wav")
            write_wav(path, output)
            rendered[slug] = output
            manifest.append({
                "slug": slug,
                "text": text,
                "group": group,
                "fgm_id": fgm_id,
                "fgm_table_id": table_id,
                "sounds2_sample_id": sample_id,
                "table_cents": table_cents,
                "note_cents": note_cents,
                "total_cents": total_cents,
                "pitch_ratio": ratio,
                "quantized_pitch_q15": quantized_pitch,
                "raw_samples": len(pcm),
                "rendered_samples": len(output),
                "rendered_seconds": round(len(output) / OUTPUT_RATE, 6),
                "output_rate": OUTPUT_RATE,
                "path": os.path.relpath(path, args.outdir),
            })

    name_audio = montage([rendered[slug] for slug, _, _ in NAME_LINES])
    phrase_audio = montage([rendered[slug] for slug, _, _ in PHRASE_LINES])
    write_wav(os.path.join(args.outdir, "conditioning_style.wav"), name_audio)
    write_wav(os.path.join(args.outdir, "conditioning_identity.wav"), phrase_audio)

    with open(os.path.join(args.outdir, "manifest.json"), "w") as dst:
        json.dump({
            "source": "BattleShip/baserom.us.z64 (US)",
            "output_rate": OUTPUT_RATE,
            "resampler": "SSB64 port N64 4-tap table, Q15 pitch",
            "style_order": [text for _, text, _ in NAME_LINES],
            "identity_order": [text for _, text, _ in PHRASE_LINES],
            "clips": manifest,
        }, dst, indent=2)
        dst.write("\n")

    print("rendered %d clips at %d Hz -> %s" %
          (len(manifest), OUTPUT_RATE, args.outdir))
    for item in manifest:
        print("%-26s sample=%3d cents=%5d seconds=%.3f" %
              (item["slug"], item["sounds2_sample_id"], item["total_cents"],
               item["rendered_seconds"]))


if __name__ == "__main__":
    sys.exit(main())
