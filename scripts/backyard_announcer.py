#!/usr/bin/env python3
"""Local announcer clips — no Fal/MiniMax needed.

Uses macOS `say` (Daniel en_GB, slightly slowed) to render "<Display>!" as
16-bit mono WAVs into play/ui/<slug>/announcer.wav — the same path the
pipeline's voice stage writes, so baked_roster validation and the engine's
VS splash pick them up unchanged.

Upgrade path: run pipeline/run_character.py --force-stage voice with
FAL_KEY + MINIMAX_ANNOUNCER_VOICE_ID to replace these with the cloned
N64-announcer voice.

Usage: python3 scripts/backyard_announcer.py [--slug X] [--force] [--voice Daniel] [--rate 165]
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(HERE, "web-prototype", "config", "backyard-starter.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", help="only this starter slug")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--voice", default="Daniel")
    ap.add_argument("--rate", default="165")
    args = ap.parse_args()

    entries = json.load(open(CONFIG))
    if args.slug:
        entries = [e for e in entries if e["slug"] == args.slug]
        if not entries:
            sys.exit(f"unknown slug {args.slug}")
    for e in entries:
        wav = os.path.join(HERE, "play", "ui", e["slug"], "announcer.wav")
        if os.path.exists(wav) and not args.force:
            print(f"skip {e['slug']} (exists)")
            continue
        os.makedirs(os.path.dirname(wav), exist_ok=True)
        text = e["display"].strip() + "!"
        r = subprocess.run(["say", "-v", args.voice, "-r", args.rate,
                            "--data-format=LEI16@22050", "-o", wav, text],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"say failed for {e['slug']}: {r.stderr[-500:]}")
        print(f"announced {e['slug']}: {text!r} ({os.path.getsize(wav)//1024} KB)")


if __name__ == "__main__":
    main()
