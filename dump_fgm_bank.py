#!/usr/bin/env python3
"""Decode raw samples from an SSB64 sound bank into WAVs.

The announcer clips live in B1_sounds2_ctl / B1_sounds2_tbl.  CTL holds the
ALBankFile struct tree with
big-endian offsets relative to the CTL base; TBL is the raw VADPCM stream.

Important: these are the raw waveforms, not game-rate FGM renders.  FGM
programs apply per-sound pitch shifts before mixing at 32 kHz.  Use
render_announcer_refs.py for announcer clips at their in-game pitch.

The VADPCM decoder is a direct port of aADPCMdecImpl in
BattleShip/port/audio/mixer.c so the output is bit-identical to what the
game's software mixer produces.

Usage:
  dump_fgm_bank.py OUTDIR [--rom path] [--segment sounds2]
"""
import argparse
import json
import os
import struct
import sys
import wave

# ROM segment table from BattleShip/yamls/us/audio.yml
SEGMENTS = {
    "sounds1": {"ctl": (0xB4E5C0, 0x6720), "tbl": (0xB54CE0, 0x116970)},
    "sounds2": {"ctl": (0xC6B650, 0xFBA0), "tbl": (0xC7B1F0, 0x2DC1E0)},
}

AL_ADPCM_WAVE = 0
AL_RAW16_WAVE = 1


def be(fmt, buf, off):
    return struct.unpack_from(">" + fmt, buf, off)


def clamp16(v):
    return -32768 if v < -32768 else (32767 if v > 32767 else v)


def _predict(byte, mask, lshift, rshift):
    """mixer.c adpcm_predict_sample: truncate to int16, then arithmetic shift."""
    v = ((byte & mask) << lshift) & 0xFFFF
    if v >= 0x8000:
        v -= 0x10000
    return v >> rshift


def decode_vadpcm(data, book, order, npredictors):
    """Port of aADPCMdecImpl (4-bit path, A_INIT state).

    book is a flat s16 list laid out [npredictors][order][8].
    """
    if order != 2:
        raise ValueError("only order-2 books are supported (mixer.c assumes 2)")
    tbls = []
    for p in range(npredictors):
        base = p * order * 8
        tbls.append((book[base:base + 8], book[base + 8:base + 16]))

    out = [0] * 16  # A_INIT: 16 samples of zeroed state precede the output
    nframes = len(data) // 9
    for f in range(nframes):
        frame = data[f * 9:(f + 1) * 9]
        shift = frame[0] >> 4
        idx = frame[0] & 0xF
        if idx >= npredictors:
            idx = 0
        t0, t1 = tbls[idx]
        rshift = (12 - shift) if shift < 12 else 0
        pos = 1
        for _half in range(2):
            prev1 = out[-1]
            prev2 = out[-2]
            ins = []
            for _j in range(4):
                byte = frame[pos]
                pos += 1
                ins.append(_predict(byte, 0xF0, 8, rshift))
                ins.append(_predict(byte, 0x0F, 12, rshift))
            for j in range(8):
                acc = t0[j] * prev2 + t1[j] * prev1 + (ins[j] << 11)
                for k in range(j):
                    acc += t1[j - k - 1] * ins[k]
                acc >>= 11  # arithmetic shift, matches C on gcc/clang
                out.append(clamp16(acc))
    return out[16:]


def decode_raw16(data):
    n = len(data) // 2
    return list(struct.unpack(">%dh" % n, data[:n * 2]))


class Ctl:
    def __init__(self, ctl, tbl):
        self.ctl = ctl
        self.tbl = tbl

    def wavetable(self, off):
        base, length, wtype, flags = be("IiBB", self.ctl, off)
        info_off = off + 12
        wt = {"base": base, "len": length, "type": wtype, "flags": flags}
        if wtype == AL_ADPCM_WAVE:
            loop_off, book_off = be("II", self.ctl, info_off)
            wt["loop"] = loop_off
            order, npred = be("ii", self.ctl, book_off)
            count = order * npred * 8
            wt["order"] = order
            wt["npredictors"] = npred
            wt["book"] = list(be("%dh" % count, self.ctl, book_off + 8))
        return wt

    def keymap(self, off):
        if off == 0:
            return None
        vmin, vmax, kmin, kmax, kbase, detune = be("BBBBBb", self.ctl, off)
        return {"velocityMin": vmin, "velocityMax": vmax, "keyMin": kmin,
                "keyMax": kmax, "keyBase": kbase, "detune": detune}

    def sound(self, off):
        env, keymap, wavetable = be("III", self.ctl, off)
        pan, vol, flags = be("BBB", self.ctl, off + 12)
        return {"envelope": env, "keymap": self.keymap(keymap),
                "wavetable": self.wavetable(wavetable),
                "pan": pan, "volume": vol, "flags": flags}

    def instrument(self, off):
        vol, pan, prio, flags = be("BBBB", self.ctl, off)
        bend, count = be("hh", self.ctl, off + 12)
        ptrs = be("%dI" % count, self.ctl, off + 16) if count > 0 else ()
        return {"volume": vol, "pan": pan, "priority": prio,
                "soundCount": count,
                "sounds": [self.sound(p) for p in ptrs if p]}

    def bank(self, off):
        # s16 instCount, u8 flags, u8 pad, s32 sampleRate, ptr percussion,
        # then instArray at +12.
        inst_count = be("h", self.ctl, off)[0]
        sample_rate = be("i", self.ctl, off + 4)[0]
        ptrs = be("%dI" % inst_count, self.ctl, off + 12) if inst_count > 0 else ()
        return {"instCount": inst_count, "sampleRate": sample_rate,
                "instruments": [self.instrument(p) for p in ptrs if p]}

    def parse(self):
        revision, bank_count = be("hh", self.ctl, 0)
        ptrs = be("%dI" % bank_count, self.ctl, 4)
        return {"revision": revision, "bankCount": bank_count,
                "banks": [self.bank(p) for p in ptrs if p]}


def write_wav(path, samples, rate):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--rom", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "BattleShip", "baserom.us.z64"))
    ap.add_argument("--segment", default="sounds2")
    args = ap.parse_args()

    seg = SEGMENTS[args.segment]
    with open(args.rom, "rb") as f:
        rom = f.read()
    co, cs = seg["ctl"]
    to, ts = seg["tbl"]
    ctl = rom[co:co + cs]
    tbl = rom[to:to + ts]
    print("CTL %d bytes, TBL %d bytes" % (len(ctl), len(tbl)))

    parsed = Ctl(ctl, tbl).parse()
    print("revision=%d bankCount=%d" % (parsed["revision"], parsed["bankCount"]))

    os.makedirs(args.outdir, exist_ok=True)
    manifest = []
    for bi, bank in enumerate(parsed["banks"]):
        rate = bank["sampleRate"]
        print("bank %d: %d instruments @ %d Hz" % (bi, bank["instCount"], rate))
        for ii, inst in enumerate(bank["instruments"]):
            for si, snd in enumerate(inst["sounds"]):
                wt = snd["wavetable"]
                raw = tbl[wt["base"]:wt["base"] + wt["len"]]
                if wt["type"] == AL_ADPCM_WAVE:
                    pcm = decode_vadpcm(raw, wt["book"], wt["order"], wt["npredictors"])
                else:
                    pcm = decode_raw16(raw)
                if not pcm:
                    continue
                name = "b%d_i%03d_s%d" % (bi, ii, si)
                path = os.path.join(args.outdir, name + ".wav")
                write_wav(path, pcm, rate)
                km = snd["keymap"] or {}
                manifest.append({
                    "name": name, "bank": bi, "inst": ii, "sound": si,
                    "samples": len(pcm), "seconds": round(len(pcm) / rate, 4),
                    "rate": rate, "type": wt["type"],
                    "keyBase": km.get("keyBase"), "detune": km.get("detune"),
                    "tblOffset": wt["base"], "tblLen": wt["len"],
                })
    with open(os.path.join(args.outdir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print("wrote %d wavs -> %s" % (len(manifest), args.outdir))


if __name__ == "__main__":
    sys.exit(main())
