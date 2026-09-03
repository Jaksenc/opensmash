# Character announcer generation

The accepted implementation is `pipeline/generate_announcer.py`. It uses the persistent
MiniMax clone made from the corrected, game-rate SSB64 announcer reference.
(The earlier OpenAI/WORLD experiment and the time-compression pass were
discarded.)

`pipeline/announcer_voice.py` is the standalone path: it imports
`pipeline.generate_announcer.generate_announcer()` (same library, no duplicated
generation code), writes `play/ui/<slug>/announcer.wav`, and stages the clip
into `../BattleShip/web-dist/bundles/<slug>.wav`:

```sh
python3 pipeline/announcer_voice.py "Queen Elizabeth the Second" --slug queen
```

`pipeline/run_character.py`'s voice stage runs the same wrapper with `--no-stage`
(its own stage step does the copy).

## Setup

```sh
python -m pip install -r requirements.txt
```

`.env` must contain `FAL_KEY` and `MINIMAX_ANNOUNCER_VOICE_ID`. The file is
ignored by git; `.env.example` lists the variable names without secrets.

## Making the voice clone

The voice id is a MiniMax clone of the game's announcer. The reference it is
built from is rendered out of the ROM by `pipeline/render_announcer_refs.py`
(`tools/derive_from_rom.py` runs it): `conditioning_style.wav` is the twelve
fighter names at in-game pitch (14 s), `conditioning_identity.wav` the menu
phrases (10 s). To create the clone on your own fal account:

```sh
python3 pipeline/create_announcer_voice.py
```

It uploads the name montage, calls `fal-ai/minimax/voice-clone` with a short
preview line, saves the preview as `announcer-clone-preview.wav`, and prints
`MINIMAX_ANNOUNCER_VOICE_ID=...` to paste into `.env`. `--audio` swaps the
reference, `--dry-run` shows the request without spending anything. MiniMax
charges per clone, and a clone unused for TTS for seven days is deleted, so
generate a clip soon after. Judge the preview by ear (see the notes at the
bottom of this file on why metrics don't work).

## Command line

```sh
python3 pipeline/generate_announcer.py "Queen Elizabeth the Second" \
  --out build/queen-announcer.wav
```

The output is mono, 32 kHz, 16-bit PCM WAV, trimmed to fixed lead/tail silence. Native MiniMax timing is used.

## Python integration

```python
from pipeline.generate_announcer import generate_announcer

generate_announcer(character_name, output_wav)
```

The function sends the supplied name as one TTS request, adding only a final
exclamation mark unless `append_exclamation=False` is passed.

## In-game injection

`pipeline/run_character.py` runs this as its `voice` stage (output
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

## Provider settings (2026-09-02)

`language_boost="English"` is the default again and `english_normalization`
stays off. Clips are trimmed to a fixed 40 ms lead / 150 ms tail of silence
(`--no-trim` keeps the provider's padding). History: the boost was dropped on
2026-08-27 because it destabilized the clone on non-English names (first
heard on "Boyang Niu"). A nine-name A/B by ear on 2026-09-02 found the
unboosted clips read non-American on ordinary names and the boost was "way
better", so it is on for every name; the non-English drift is the accepted
cost until phonetic respelling lands. Both remain overridable per call
(`english_normalization=`, `language_boost=`, or the matching CLI flags).

Better but not adopted: respelling the name phonetically ("Bo-Yang Nyoo")
sounded clearly best of everything tried. It needs a per-character
pronunciation that does not exist yet — the natural home is a `phonetic`
field from `pipeline/expand_character.py`, generated in the same OpenAI call as
`short`/`emblem`. Deferred because a wrong respelling yields a confidently
mispronounced name with nothing to catch it.

Ruled out: `language_boost="Chinese"` (worse than either), and an English
carrier phrase ("Get ready. <name>!") trimmed back to the name — the trim
degraded the result and it reverses this file's no-prompt-expansion rule.

**Judge these by ear.** Two acoustic proxies were tried and both failed:
clip RMS (a control re-run of an existing roster name came out just as
"hot", so the stored roster levels are simply stale) and long-term-average-
spectrum distance to a roster centroid (leave-one-out shows the roster's own
internal spread, 2.26–4.08, is wider than the gap between a clip that sounds
right and one that does not — it scored a known-bad take identically to a
known-good one). Do not gate voice regeneration on either.
