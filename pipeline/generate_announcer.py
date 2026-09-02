#!/usr/bin/env python3
"""Generate one SSB64-style character announcement with the MiniMax clone.

Command line:
    python3 pipeline/generate_announcer.py "Mao Zedong" --out build/mao.wav

Python:
    from generate_announcer import generate_announcer
    generate_announcer("Mao Zedong", "build/mao.wav")

Configuration is read from environment variables first, then from the .env
file at the repository root:

    FAL_KEY
    MINIMAX_ANNOUNCER_VOICE_ID

This is the accepted native-timing path (the discarded OpenAI/WORLD
experiment is gone; announcer_voice.py is now a thin staging wrapper around
this module). No time compression is applied.

Provider settings: language_boost is left unset and english_normalization
off. Forcing them to English destabilized the voice clone on non-English
names (heard first on "Boyang Niu"); with the boost dropped the clone stays
in character. English names are unaffected. Both are still overridable per
call for A/B work.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request


MODEL = "fal-ai/minimax/speech-02-hd"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries without requiring python-dotenv."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _require_configuration() -> str:
    _load_env_file(PROJECT_ROOT / ".env")
    if not os.environ.get("FAL_KEY"):
        raise RuntimeError(
            "FAL_KEY is missing; set it in the environment or .env"
        )
    voice_id = os.environ.get("MINIMAX_ANNOUNCER_VOICE_ID")
    if not voice_id:
        raise RuntimeError(
            "MINIMAX_ANNOUNCER_VOICE_ID is missing; set it in the environment "
            "or .env"
        )
    return voice_id


def _fal_client():
    try:
        import fal_client
    except ImportError as exc:
        raise RuntimeError(
            "fal-client is not installed; run: "
            "python -m pip install -r requirements.txt"
        ) from exc
    return fal_client


def generate_announcer(
    name: str,
    output_path: str | os.PathLike[str],
    *,
    speed: float = 1.0,
    append_exclamation: bool = True,
    english_normalization: bool = False,
    language_boost: str | None = None,
) -> Path:
    """Generate a mono 32 kHz PCM WAV for one character name.

    The provider receives exactly the supplied name, with a terminal
    exclamation mark added by default. No prompt expansion, prosody transfer,
    silence removal, or time compression is performed.
    """
    name = name.strip()
    if not name:
        raise ValueError("name must not be empty")
    if not 0.5 <= speed <= 2.0:
        raise ValueError("speed must be between 0.5 and 2.0")

    output = Path(output_path).expanduser().resolve()
    if output.suffix.lower() != ".wav":
        raise ValueError("output_path must end in .wav")
    output.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to decode the provider audio to WAV")

    voice_id = _require_configuration()
    fal_client = _fal_client()
    text = name if not append_exclamation or name.endswith("!") else f"{name}!"

    arguments = {
        "text": text,
        "voice_setting": {
            "voice_id": voice_id,
            "speed": speed,
            "vol": 1.0,
            "pitch": 0,
            "english_normalization": english_normalization,
        },
        "output_format": "url",
    }
    if language_boost:
        arguments["language_boost"] = language_boost

    result = fal_client.subscribe(MODEL, arguments=arguments)
    audio_url = result["audio"]["url"]

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".provider-audio", delete=False) as tmp:
            temporary_path = Path(tmp.name)
        urllib.request.urlretrieve(audio_url, temporary_path)
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(temporary_path),
                "-ar",
                "32000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(output),
            ],
            check=True,
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate an SSB64-style announcer WAV for one character name."
    )
    parser.add_argument("name", help="character name to announce")
    parser.add_argument("--out", required=True, type=Path, help="output .wav path")
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="MiniMax native speed control, 0.5-2.0 (default: 1.0)",
    )
    parser.add_argument(
        "--no-exclamation",
        action="store_true",
        help="do not append an exclamation mark to the supplied name",
    )
    parser.add_argument(
        "--english-normalization",
        action="store_true",
        help="re-enable MiniMax english_normalization (default: off)",
    )
    parser.add_argument(
        "--language-boost",
        default=None,
        help="MiniMax language_boost, e.g. English (default: unset)",
    )
    args = parser.parse_args()

    output = generate_announcer(
        args.name,
        args.out,
        speed=args.speed,
        append_exclamation=not args.no_exclamation,
        english_normalization=args.english_normalization,
        language_boost=args.language_boost,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
