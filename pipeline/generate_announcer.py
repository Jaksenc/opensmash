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

Provider settings: language_boost defaults to "English" — an A/B by ear on
2026-09-02 found the boost gives the clone a clearly more American read
across the roster, which outweighs the drift it caused on a few non-English
names (heard first on "Boyang Niu", 2026-08-27). english_normalization stays
off. Both remain overridable per call for A/B work. Clips are trimmed to
fixed lead/tail silence.
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
    language_boost: str | None = "English",
    trim: bool = True,
) -> Path:
    """Generate a mono 32 kHz PCM WAV for one character name.

    The provider receives exactly the supplied name, with a terminal
    exclamation mark added by default. No prompt expansion, prosody transfer,
    or time compression is performed. With ``trim`` (default) the leading and
    trailing silence is cut to a fixed pad so every clip starts and ends alike.
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

    if trim:
        trim_silence(output)
    return output


TRIM_LEAD_S = 0.04
TRIM_TAIL_S = 0.15
TRIM_THRESHOLD = 0.05  # fraction of the clip peak


def trim_silence(path: str | os.PathLike[str], lead_s: float = TRIM_LEAD_S,
                 tail_s: float = TRIM_TAIL_S, threshold: float = TRIM_THRESHOLD) -> None:
    """Cut leading/trailing silence of a 16-bit mono WAV to fixed pads.

    Silence is anything under ``threshold`` x the clip peak, measured in 5 ms
    windows. Existing silence shorter than the pad is kept as is (no padding
    is synthesised). Rewrites the file in place.
    """
    import array
    import wave

    path = Path(path)
    with wave.open(str(path), "rb") as w:
        params = w.getparams()
        frames = w.readframes(w.getnframes())
    if params.sampwidth != 2 or params.nchannels != 1:
        raise ValueError("trim_silence expects 16-bit mono PCM")
    samples = array.array("h", frames)
    sr = params.framerate
    win = max(1, sr // 200)
    peak = max((abs(x) for x in samples), default=0)
    if peak == 0:
        return
    gate = peak * threshold
    loud = [i for i in range(0, len(samples), win)
            if max(abs(x) for x in samples[i:i + win]) > gate]
    if not loud:
        return
    start = max(0, loud[0] - int(lead_s * sr))
    end = min(len(samples), loud[-1] + win + int(tail_s * sr))
    if start == 0 and end == len(samples):
        return
    with wave.open(str(path), "wb") as w:
        w.setparams(params)
        w.writeframes(samples[start:end].tobytes())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate an SSB64-style announcer WAV for one character name."
    )
    parser.add_argument("name", help="character name to announce")
    parser.add_argument("--out", required=True, type=Path, help="output .wav path")
    parser.add_argument(
        "--no-trim", action="store_true",
        help="keep the provider's leading/trailing silence instead of trimming to fixed pads",
    )
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
        default="English",
        help="MiniMax language_boost, or none to unset (default: English)",
    )
    args = parser.parse_args()

    output = generate_announcer(
        args.name,
        args.out,
        speed=args.speed,
        append_exclamation=not args.no_exclamation,
        english_normalization=args.english_normalization,
        language_boost=None if args.language_boost == "none" else args.language_boost,
        trim=not args.no_trim,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
