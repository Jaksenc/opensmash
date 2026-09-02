#!/usr/bin/env python3
"""Create the announcer voice clone on fal (MiniMax) and print its voice id.

    python3 pipeline/create_announcer_voice.py
    python3 pipeline/create_announcer_voice.py --audio my-reference.wav --preview out.wav

The generator (pipeline/generate_announcer.py) speaks every announcer clip
with a MiniMax voice clone of the game's announcer, addressed by
MINIMAX_ANNOUNCER_VOICE_ID in .env. This script makes that clone from the
reference montage rendered out of the ROM by pipeline/render_announcer_refs.py
(eval/announcer_conditioning_corrected/conditioning_style.wav: the twelve
fighter names at in-game pitch, 14 s; the endpoint needs at least 10 s).

Needs FAL_KEY in the environment or .env. MiniMax bills a small fee per
clone. A clone that is not used for TTS within seven days is deleted, so
generate at least one announcer clip after creating it (the preview this
script requests counts).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline"))
from generate_announcer import _fal_client, _load_env_file  # noqa: E402

ENDPOINT = "fal-ai/minimax/voice-clone"
DEFAULT_AUDIO = (PROJECT_ROOT / "eval" / "announcer_conditioning_corrected"
                 / "conditioning_style.wav")
DEFAULT_PREVIEW_TEXT = "Mario!"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audio", type=Path, default=DEFAULT_AUDIO,
                    help="reference WAV, at least 10 s (default: the ROM-rendered name montage)")
    ap.add_argument("--preview-text", default=DEFAULT_PREVIEW_TEXT,
                    help="line the endpoint speaks back as a preview of the clone")
    ap.add_argument("--preview", type=Path, default=Path("announcer-clone-preview.wav"),
                    help="where to save the preview (mono 32 kHz WAV; needs ffmpeg)")
    ap.add_argument("--model", default="speech-02-hd",
                    choices=["speech-02-hd", "speech-02-turbo", "speech-01-hd", "speech-01-turbo"],
                    help="TTS model the clone is prepared for; generate_announcer.py uses speech-02-hd")
    ap.add_argument("--noise-reduction", action="store_true",
                    help="ask MiniMax to denoise the reference first (the ROM render is already clean)")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be sent and exit without calling fal")
    a = ap.parse_args(argv)

    if not a.audio.is_file():
        print(f"reference audio not found: {a.audio}\n"
              "render it with: python3 tools/derive_from_rom.py", file=sys.stderr)
        return 2
    arguments = {"text": a.preview_text, "model": a.model}
    if a.noise_reduction:
        arguments["noise_reduction"] = True
    print(f"reference: {a.audio} ({a.audio.stat().st_size} bytes)")
    print(f"endpoint:  {ENDPOINT}  arguments: {arguments}")
    if a.dry_run:
        return 0

    _load_env_file(PROJECT_ROOT / ".env")
    if not os.environ.get("FAL_KEY"):
        print("FAL_KEY is missing; set it in the environment or .env", file=sys.stderr)
        return 2
    fal_client = _fal_client()

    print("uploading reference audio ...")
    arguments["audio_url"] = fal_client.upload_file(str(a.audio))
    print("cloning ...")
    result = fal_client.subscribe(ENDPOINT, arguments=arguments)
    voice_id = result.get("custom_voice_id")
    if not voice_id:
        print(f"no custom_voice_id in response: {result}", file=sys.stderr)
        return 1

    preview_url = (result.get("audio") or {}).get("url")
    if preview_url:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            with tempfile.NamedTemporaryFile(suffix=".provider-audio", delete=False) as tmp:
                raw = Path(tmp.name)
            try:
                urllib.request.urlretrieve(preview_url, raw)
                a.preview.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(raw),
                                "-ac", "1", "-ar", "32000", "-sample_fmt", "s16", str(a.preview)],
                               check=True)
                print(f"preview:   {a.preview}")
            finally:
                raw.unlink(missing_ok=True)
        else:
            print(f"preview:   {preview_url}  (ffmpeg not found; not converted)")

    print()
    print(f"MINIMAX_ANNOUNCER_VOICE_ID={voice_id}")
    print("add that line to .env, then listen to the preview before generating a roster.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
