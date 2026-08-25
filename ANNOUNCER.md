# Character announcer generation

The accepted implementation is `generate_announcer.py`. It uses the persistent
MiniMax clone made from the corrected, game-rate SSB64 announcer reference.
It does not use `announcer_voice.py`, the earlier OpenAI/WORLD experiment, and
does not apply the discarded time-compression pass.

## Setup

```sh
cd pipeline
python -m pip install -r requirements-announcer.txt
```

`pipeline/.env` must contain `FAL_KEY` and
`MINIMAX_ANNOUNCER_VOICE_ID`. The file is ignored by git; `.env.example` lists
the required variable names without secrets.

## Command line

```sh
python generate_announcer.py "Queen Elizabeth the Second" \
  --out build/queen-announcer.wav
```

The output is mono, 32 kHz, 16-bit PCM WAV. Native MiniMax timing is used.

## Python integration

```python
from generate_announcer import generate_announcer

generate_announcer(character_name, output_wav)
```

The function sends the supplied name as one TTS request, adding only a final
exclamation mark unless `append_exclamation=False` is passed.
