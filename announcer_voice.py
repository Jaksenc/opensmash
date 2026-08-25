#!/usr/bin/env python3
"""Standalone announcer-voice path for one character.

Generates the announcer clip for a character and stages it into the web
harness, without running the rest of run_character.py. Generation is
generate_announcer.generate_announcer() — the same library run_character's
voice stage uses; this file adds only slug/paths/staging.

  announcer_voice.py "Queen Elizabeth the Second"             # gen + stage
  announcer_voice.py "Queen Elizabeth the Second" --slug queen
  announcer_voice.py "Some Name" --out foo.wav --no-stage     # bare clip

Default output is play/ui/<slug>/announcer.wav; staging copies it to
BattleShip/web-dist/bundles/<slug>.wav and prints the inject_voice URL
parameter for the play harness.

(The earlier OpenAI/WORLD prosody-transfer experiment that lived in this
file was discarded; see ANNOUNCER.md.)
"""
import argparse
import os
import re
import shutil

from generate_announcer import generate_announcer

HERE = os.path.dirname(os.path.abspath(__file__))
WEBDIST = os.path.join(HERE, "..", "BattleShip", "web-dist", "bundles")


def name_slug(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())[:16]


def generate_and_stage(display, slug=None, out=None, speed=1.0, stage=True):
    """Generate the clip (shared library) and optionally stage it for play.

    Returns (wav_path, staged_path_or_None).
    """
    slug = slug or name_slug(display)
    out = out or os.path.join(HERE, "play", "ui", slug, "announcer.wav")
    wav = generate_announcer(display, out, speed=speed)
    staged = None
    if stage and os.path.isdir(WEBDIST):
        staged = os.path.join(WEBDIST, f"{slug}.wav")
        shutil.copyfile(wav, staged)
    return wav, staged


def main():
    ap = argparse.ArgumentParser(
        description="Generate + stage the announcer clip for one character.")
    ap.add_argument("name", help="character display name to announce")
    ap.add_argument("--slug", default=None, help="bundle slug (default: from name)")
    ap.add_argument("--out", default=None, help="output .wav (default: play/ui/<slug>/announcer.wav)")
    ap.add_argument("--speed", type=float, default=1.0, help="MiniMax speed, 0.5-2.0")
    ap.add_argument("--no-stage", action="store_true", help="skip the web-dist/bundles copy")
    a = ap.parse_args()

    slug = a.slug or name_slug(a.name)
    wav, staged = generate_and_stage(a.name, slug=slug, out=a.out,
                                     speed=a.speed, stage=not a.no_stage)
    print(wav)
    if staged:
        print(staged)
        print(f"url param: &inject_voice=bundles/{slug}.wav")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
