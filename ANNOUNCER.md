# Character announcer generation

The accepted implementation is `generate_announcer.py`. It uses the persistent
MiniMax clone made from the corrected, game-rate SSB64 announcer reference.
(The earlier OpenAI/WORLD experiment and the time-compression pass were
discarded.)

`announcer_voice.py` is the standalone path: it imports
`generate_announcer.generate_announcer()` (same library, no duplicated
generation code), writes `play/ui/<slug>/announcer.wav`, and stages the clip
into `../BattleShip/web-dist/bundles/<slug>.wav`:

```sh
python announcer_voice.py "Queen Elizabeth the Second" --slug queen
```

`run_character.py`'s voice stage runs the same wrapper with `--no-stage`
(its own stage step does the copy).

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

## In-game injection

`run_character.py` runs this as its `voice` stage (output
`play/ui/<slug>/announcer.wav`), stages the clip into
`web-dist/bundles/<slug>.wav`, and adds `&inject_voice=bundles/<slug>.wav`
to the play URL.

Game side, the web shell fetches the clip into MEMFS and sets
`SSB64_INJECT_VOICE`. `port/audio/voice_inject.c` mixes the WAV straight
into the 32 kHz output; a hook in `func_800269C0_275C0` (n_env.c) swaps it
in whenever the injected fkind's announcer name would play (character
select, VS results winner announce, etc.), so there is no FGM sample-length
limit. VS results also stretches the hardcoded 60-tic gap before the crowd
cheer to fit longer clips (`port_voice_results_extra_wait_tics`).

Known gaps: the clip ignores the in-game voice-volume slider, and only the
name line is generated (team-battle / 1P-mode announcer lines stay vanilla).
