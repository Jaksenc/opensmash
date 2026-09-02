# OpenSmash

Super Smash Bros. 64 in the browser, with AI-generated fighters. Give it a
name and (optionally) a photo, and the pipeline produces a low-poly rigged
mesh, a character-select portrait, a stock icon, a series emblem, and an
announcer call, then injects the result into the game on one of the twelve
original skeletons.

No Nintendo assets are in this repo or served by the site. The engine is
[BattleShip](https://github.com/turtlesoupy/BattleShip), a decomp-based PC
port, and the game's assets are extracted in the player's browser from their
own ROM.

## Upstream projects

Everything below the site is a chain of forks. We keep our own copies of each
so the wasm build and the pipeline hooks stay pinned; the BattleShip
submodules point at these copies.

| Our copy | Forked from | What it is |
|---|---|---|
| [turtlesoupy/BattleShip](https://github.com/turtlesoupy/BattleShip) | [JRickey/BattleShip](https://github.com/JRickey/BattleShip) | The PC port: native macOS/Linux/Windows/Android plus our Emscripten build, the fighter-injection code (`port/`), and the pipeline dump hooks. |
| [turtlesoupy/ssb-decomp-re](https://github.com/turtlesoupy/ssb-decomp-re) | [VetriTheRetri/ssb-decomp-re](https://github.com/VetriTheRetri/ssb-decomp-re) | The game decompilation. BattleShip vendors it as `decomp/`. |
| [turtlesoupy/libultraship](https://github.com/turtlesoupy/libultraship) | [JRickey/libultraship](https://github.com/JRickey/libultraship/tree/ssb64) ← [Kenix3/libultraship](https://github.com/Kenix3/libultraship) | Rendering, audio, and input layer for N64 ports. Vendored as `libultraship/`. |
| [turtlesoupy/Torch](https://github.com/turtlesoupy/Torch) | [JRickey/Torch](https://github.com/JRickey/Torch/tree/ssb64) ← [HarbourMasters/Torch](https://github.com/HarbourMasters/Torch) | Extracts assets from the ROM into the `.o2r` archive. We also compile it to wasm so the browser can do this. Vendored as `torch/`. |

BattleShip's own README covers licenses and credits for those projects.

## Layout

| | Where | What |
|---|---|---|
| Engine | sibling repo `BattleShip/` | The game, built to WebAssembly. Ships Torch compiled to wasm so the browser can build the asset archive from the ROM. |
| Generator | `pipeline/` | Python. `run_character.py` turns a name + photo into a playable fighter. |
| Website | `web-prototype/` | React site + Node server. Character grid, ROM check, launching the engine, and the hosted "create a fighter" flow (Cloud Run, Firestore, GCS). |
| Skeletons | `skels/` | The twelve target skeletons, per-fighter conform profiles, and the reference part data the converter fits meshes onto. |
| Roster | `play/` (gitignored) + GCS | Local generation output. The production roster lives in a public GCS bucket, pinned by `web-prototype/config/baked-assets.json`. |

Also: `scripts/` (batch driver), `tools/` (utilities), `eval/` (mesh eval
harness, see `EVAL.md`), `config/` (roster lists), `docs/`.
`requirements.txt` is the Python dependency list.

## Clone layout

The two repos sit next to each other, with emsdk alongside:

```
opensmash/
  BattleShip/    git clone https://github.com/turtlesoupy/BattleShip
  pipeline/      git clone https://github.com/turtlesoupy/opensmash   (this repo)
  emsdk/         https://github.com/emscripten-core/emsdk
```

The server looks for the engine at `pipeline/BattleShip/web-dist`, then
`../BattleShip/web-dist`. A symlink (`ln -s ../BattleShip pipeline/BattleShip`)
or the sibling layout both work.

You need:

- Node 20+ and pnpm (`corepack enable`; the lockfile pins pnpm 11).
- Python 3.11+ and `pip install -r requirements.txt`, plus `ffmpeg` for
  announcer audio.
- A Super Smash Bros. USA (NTSC-U v1.0) ROM, SHA-1
  `e2929e10fccc0aa84e5776227e798abc07cedabf`. Don't commit it. Other regions
  are rejected; the engine is built per region.
- Emscripten, if you're building the engine yourself.
- API keys, if you're generating fighters (below).

## Running the site locally

### 1. Build the engine

From `BattleShip/`, with the ROM at its root as `baserom.us.z64` and emsdk
activated (`source ../emsdk/emsdk_env.sh`):

```bash
emcmake cmake -B build-wasm -G Ninja -DCMAKE_BUILD_TYPE=Release -DSSB64_VERSION=us
```

```bash
cmake --build build-wasm --target BattleShip.js -j
```

```bash
scripts/build_torch_wasm.sh
```

```bash
scripts/package_web.sh build-wasm web-dist
```

`web-dist/` is what the site serves under `/engine/`. Every file URL in it
carries a build version, and it does not include the ROM-derived archive;
the browser builds that on first launch (`BattleShip/docs/web_rom_extraction.md`).
After C changes: `ninja -C build-wasm BattleShip.js`, then `package_web.sh`
again.

### 2. Get a roster

Download the production roster (1000+ fighters, ~3.3 GB) into
`web-prototype/.baked-characters`:

```bash
cd web-prototype && PUBLIC_BUCKET=smash-the-weights-fighter-assets pnpm assets:fetch
```

Or generate your own into `play/` (next section). In dev the server reads
`play/` directly.

### 3. Start it

```bash
cd web-prototype && pnpm install && pnpm dev:safe
```

Open <http://127.0.0.1:4174>, drop in the ROM, play. `dev:safe` disables the
local fighter worker so `/create` can't spend credits; `pnpm dev` runs real
generations from the web UI. The ROM gate, auth, phone hand-off, and the
hosted generation flow are documented in
[`web-prototype/README.md`](web-prototype/README.md).

## Generating a fighter

### Keys

Copy `.env.example` to `.env` in the repo root (gitignored, every pipeline
script reads it):

| Key | Used for |
|---|---|
| `OPENAI_API_KEY` | Character description (`gpt-5.6-luna`); T-pose sheet, portrait, stock and emblem art (`gpt-image-2`); the facing check; upload moderation on the site. |
| `TRIPO_API_KEY` | Image-to-3D + auto-rig. ~55 credits (~$0.55) per fighter. Task ids are checkpointed, so a retry doesn't buy the mesh again. |
| `FAL_KEY` | Announcer clip (fal's MiniMax speech endpoint). |
| `MINIMAX_ANNOUNCER_VOICE_ID` | The MiniMax voice clone the announcer speaks with. You make this once from announcer reference audio; see `ANNOUNCER.md`. |
| `GEMINI_API_KEY` | Optional. Alternative image model for some experiments. |
| `MESHY_API_KEY` | Optional. Only `tools/generate_mesh.py` (site props). |

A fighter costs about $0.65 in provider fees. Each run writes a per-stage
breakdown to `play/ui/<slug>/cost.json`.

### One fighter

```bash
python3 pipeline/run_character.py "Weird Al Yankovic" --photo ref.png
```

Options: `--short WEIRDAL` (tile caption, up to 10 capital letters),
`--display "Mozart"` (in-game name and what the announcer says),
`--emblem "a red accordion"` (series emblem; inferred if omitted),
`--notes "..."` (steer the description: which depiction, outfit, era),
`--variants all` (also build the experimental DK and Yoshi targets).

Stages: `expand` (description) → `tpose` (model sheet) → `mesh` (Tripo mesh +
rig) → `convert` (fit onto the game skeletons) → `portrait` → `stock` →
`emblem` → `ui` → `voice`. A stage is skipped if its output already exists,
so a failed run resumes where it stopped. Delete a stage's output or pass
`--force-stage <stage>` to redo it. To fix a description or emblem, edit
`character.json` and re-run.

Output goes to `play/ui/<slug>/` (art, `character.json`, the `.osbui` UI pack,
`announcer.wav`, intermediates) and `play/<slug>.osb6`, one bundle with the
mesh for every target skeleton. The site's `/create` page runs this same
script.

### Many fighters

```bash
python3 scripts/batch_characters.py names.txt --workers 3
```

One name per line. Retries transient provider errors, re-rolls
moderation-blocked images, skips names that are already done, and keeps state
in `batch-state/`. `touch batch-state/STOP` to finish in-flight work and
exit. `tools/build_wikipedia_people_seed.py` builds popularity-ranked name
lists from Wikipedia; the rules for who goes on the roster are in
`docs/character-roster-editorial-policy.md`.

## Publishing to the site roster

`web-prototype/config/characters.json` is the ordered list of baked fighters.
After checking a fighter locally:

```bash
python3 pipeline/baked_roster.py <slug>
```

That validates the required files and appends the slug (`run_character.py
--publish` does the same). Then upload the runtime files and refresh the
checksum pin:

```bash
cd web-prototype && PUBLIC_BUCKET=<project>-fighter-assets pnpm assets:publish
```

Commit `config/characters.json` and `config/baked-assets.json` together.
Objects are keyed by content hash, so publishing only adds, and old commits
stay reproducible. Deploy (Cloud Run, the worker job, Cloudflare) is one
script: [`web-prototype/infra/README.md`](web-prototype/infra/README.md).

## Game-derived inputs

Some generator inputs come from the game itself. All of them can be rebuilt
from your ROM:

| Files | What they are | Rebuilt by |
|---|---|---|
| `skels/*.skel`, `skels/fk*-all.log`, `skels/parts/*.json` | The twelve fighters' rest-pose skeletons and part geometry, which the converter fits generated meshes onto | `derive_skeletons.py` (runs the engine) |
| `assets/css-font/portraits`, `assets/css-font/locked` | Character-select portrait tiles, fire slot, question mark, shadows | `derive_from_rom.py` |
| `web-prototype/visual/assets/ui_refs/` | Tile and name sprites, stock icon, emblem sheet, and the glyph atlases the UI packer composes names from | `derive_from_rom.py` (four letters need `--skeletons`) |
| `eval/announcer_conditioning_corrected/` | The announcer lines the voice clone is conditioned on, rendered at in-game pitch | `derive_from_rom.py` |
| `stone-tile-investigation/source-*` | The character-select stone texture | `derive_from_rom.py` |

Not derived: the hand-authored `skels/*.profile.json`, `skels/VALIDATION.md`,
and `assets/css-font/letters`. `skels/reference/mario.skel` is an old capture
from a different engine build that `texture_check.py` still reads; the scripts
report it as `LEGACY` and leave it alone.

Why run the engine for skeletons: the ROM stores joint trees and animations,
not world-space rest frames. The dump hook runs the game's own setup and
transform code and prints the result, which is simpler and safer than
reimplementing that in Python. The conform profiles were tuned against these
exact numbers.

### Prerequisites

- The ROM at `BattleShip/baserom.us.z64` (the script checks its SHA-1).
- A native engine build, which also extracts the `BattleShip.o2r` asset
  archive the sprite extraction reads. From `BattleShip/`:

```bash
cmake -S . -B build-us -GNinja -DSSB64_VERSION=us -DCMAKE_BUILD_TYPE=Release && cmake --build build-us -j
```

- Python with `numpy` and `Pillow`.

### Verify

```bash
python3 tools/derive_from_rom.py --verify --skeletons
```

Derives everything into a temp dir and prints one line per file:
`IDENTICAL`, `DIFFERS` plus a reason (pixel count, which joints moved), or
`LEGACY`. Non-zero exit on any difference. `--skeletons` launches
`BattleShip/build-us/BattleShip` thirteen times (once per fighter with
`SSB64_DUMP_SKELETON`, once on the character-select screen with
`SSB64_DUMP_SPRITES`). A window opens and closes each time, ~10 s per launch.
Leave it off to check just the archive-based files.

### Regenerate

```bash
python3 tools/derive_from_rom.py --skeletons
```

Without `--verify`, files are written in place. `--out DIR` writes a mirror
of the repo layout elsewhere. Also useful:

```bash
python3 tools/derive_skeletons.py --verify --fighters samus,link
```

```bash
python3 tools/derive_skeletons.py --verify --from-logs skels
```

The first limits engine runs to the named fighters (names or fkind numbers).
The second skips the engine and re-derives from the committed raw logs, which
tests the parsing and profile-map transform without a ROM. `--build-dir`
points either script at a different native build.

The `dl=` field in the skeleton dumps is a host pointer the engine prints;
the scripts normalize it to its stable low bits so two launches match. The
one consumer only checks whether it's zero.

## More docs

- `EVAL.md`: mesh generation / skinning eval harness and its experiment log.
- `ANNOUNCER.md`: announcer voice generation and the MiniMax clone.
- `docs/site-visual-assets.md`: how the site's console, cartridge, CRT intro,
  and other props were made.
- `web-prototype/docs/production-architecture.md`: the hosted generation
  service (job protocol, retries, abuse controls).
- `BattleShip/docs/`: engine internals, web harness, controller ports,
  in-browser ROM extraction.
