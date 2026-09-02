# OpenSmash / Smash the Weights

Super Smash Bros. 64 running in the browser, with a roster of AI-generated
fighters. Type a name (and optionally supply a photo) and the pipeline turns it
into a rigged, textured, low-poly fighter with a character-select portrait,
stock icon, series emblem, and an announcer call, then injects it into the game
on top of one of the original twelve skeletons.

Nothing Nintendo owns is in this repository or served by the site. The engine
is compiled from the [BattleShip](https://github.com/turtlesoupy/BattleShip)
decompilation port, and the game's assets are extracted inside the player's
browser from a ROM they already own.

## How the pieces fit

| Piece | Where | What it does |
|---|---|---|
| Engine | sibling repo `BattleShip/` | The game, compiled to WebAssembly with Emscripten. Includes Torch compiled to wasm so the browser can build the asset archive from the player's ROM. |
| Generator | `pipeline/` in this repo | Python scripts that turn a name + photo into a playable fighter (`run_character.py` is the one command). |
| Website | `web-prototype/` in this repo | React site + Node server: the character grid, ROM validation, launching the engine, and the hosted "create a fighter" flow (Cloud Run + Firestore + GCS in production). |
| Skeletons | `skels/` | The twelve target skeletons, per-fighter conform profiles, and the reference part data the converter fits generated meshes onto. |
| Roster | `play/` (git-ignored) and GCS | Your local generation workspace. The production roster is content-addressed in a public GCS bucket and pinned by `web-prototype/config/baked-assets.json`. |

Other directories: `scripts/` (batch generation driver), `tools/` (one-off
utilities), `eval/` (mesh-quality evaluation harness, see `EVAL.md`),
`config/` (roster lists and editorial policy inputs), `docs/`.

## Setting up a clone

The two repositories sit side by side, with the Emscripten SDK next to them:

```
opensmash/
  BattleShip/    git clone https://github.com/turtlesoupy/BattleShip
  pipeline/      git clone https://github.com/turtlesoupy/opensmash   (this repo)
  emsdk/         https://github.com/emscripten-core/emsdk
```

The site server looks for the engine at `pipeline/BattleShip/web-dist` first
and `../BattleShip/web-dist` second, so either a symlink
(`ln -s ../BattleShip pipeline/BattleShip`) or the sibling layout works.

You will need:

- **Node 20+ and pnpm** (`corepack enable`; the lockfile pins pnpm 11).
- **Python 3.11+** with `numpy scipy Pillow opencv-python-headless fal-client`
  (the same list the production worker installs, see
  `web-prototype/infra/requirements-worker.txt`), plus `ffmpeg` on your PATH
  for announcer audio.
- **A legal Super Smash Bros. (USA, NTSC-U v1.0) ROM.** SHA-1
  `e2929e10fccc0aa84e5776227e798abc07cedabf`. Never commit it. Other regions
  are recognised and rejected; the engine is region-compiled.
- **Emscripten** (only to build the engine; skip if someone hands you a built
  `web-dist`).
- **API keys** if you want to generate fighters, see below.

## Run the website locally

### 1. Build the engine once

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

`package_web.sh` produces `web-dist/`, the self-contained engine package the
site serves under `/engine/`. Every runtime URL in it carries a content-derived
build version, and the package deliberately does not contain the ROM-derived
archive; the browser rebuilds that from the player's ROM on first launch (see
`BattleShip/docs/web_rom_extraction.md`). After C changes, rebuild with
`ninja -C build-wasm BattleShip.js` and re-run `package_web.sh`.

### 2. Get a roster

Either download the pinned production roster (1000+ fighters, about 3.3 GB)
into `web-prototype/.baked-characters`:

```bash
cd web-prototype && PUBLIC_BUCKET=smash-the-weights-fighter-assets pnpm assets:fetch
```

or generate your own into `play/` (next section). In development the server
reads `play/` directly.

### 3. Start the site

```bash
cd web-prototype && pnpm install && pnpm dev:safe
```

Open <http://127.0.0.1:4174>, drop in your ROM, and play. `dev:safe` disables
the local fighter worker so clicking around `/create` cannot spend provider
credits; use `pnpm dev` to run real generations from the web UI. Details of
the ROM gate, authentication, ROM hand-off between devices, and the hosted
generation flow are in [`web-prototype/README.md`](web-prototype/README.md).

## Generate a fighter

### Keys

Copy `.env.example` to `.env` at the repository root (git-ignored; every
pipeline script reads it) and fill in:

| Key | Used for |
|---|---|
| `OPENAI_API_KEY` | Character description (`gpt-5.6-luna`), the T-pose model sheet, portrait, stock, and emblem art (`gpt-image-2`), the facing check, and the website's upload moderation. |
| `TRIPO_API_KEY` | Image-to-3D mesh and auto-rig. About 55 credits (roughly $0.55) per fighter; the paid task ids are checkpointed so a retry never buys the mesh twice. |
| `FAL_KEY` | Announcer clip via fal's MiniMax speech endpoint. |
| `MINIMAX_ANNOUNCER_VOICE_ID` | The MiniMax voice clone the announcer clip is spoken with. You create this once in MiniMax from announcer reference audio; see `ANNOUNCER.md`. |
| `GEMINI_API_KEY` | Optional. Alternative image model used by some experiments. |
| `MESHY_API_KEY` | Optional. Only `tools/generate_mesh.py` (site props), not the fighter pipeline. |

A full fighter costs about $0.65 in provider fees; each run writes a
per-stage breakdown to `play/ui/<slug>/cost.json`.

### One fighter

```bash
python3 pipeline/run_character.py "Weird Al Yankovic" --photo ref.png
```

Useful options: `--short WEIRDAL` (the in-game tile caption, up to 10
capital letters), `--display "Mozart"` (the in-game name and what the announcer
shouts), `--emblem "a red accordion"` (the series emblem, otherwise inferred),
`--notes "..."` (steer which depiction, outfit, or era the description picks),
`--variants all` (also build the experimental DK and Yoshi targets).

The stages run in order: `expand` (description) → `tpose` (model sheet) →
`mesh` (Tripo mesh + rig) → `convert` (fit onto the game skeletons) →
`portrait` → `stock` → `emblem` → `ui` → `voice`. Each stage is skipped when
its output already exists, so a failed run resumes where it stopped. Delete a
stage's output or pass `--force-stage <stage>` to redo one; editing
`character.json` and re-running is the normal way to fix a description or
emblem.

Outputs land in `play/ui/<slug>/` (art, `character.json`, the `.osbui` UI
pack, `announcer.wav`, and intermediates) plus `play/<slug>.osb6`, the single
bundle carrying the mesh for every target skeleton. The web UI's `/create`
page runs exactly this script.

### Many fighters

```bash
python3 scripts/batch_characters.py names.txt --workers 3
```

One name per line. The driver retries transient provider errors, re-rolls
moderation-blocked images, skips names that are already complete, and records
progress under `batch-state/`. Touch `batch-state/STOP` to finish in-flight
work and exit. `tools/build_wikipedia_people_seed.py` builds popularity-ranked
name lists from Wikipedia; the editorial rules for who belongs on the roster
are in `docs/character-roster-editorial-policy.md`.

## Publish fighters to the site roster

`web-prototype/config/characters.json` is the ordered allowlist of baked
fighters. After reviewing a fighter locally:

```bash
python3 pipeline/baked_roster.py <slug>
```

validates the required files and appends the slug (or pass `--publish` to
`run_character.py`). Then upload the roster's runtime files to the public
bucket and refresh the checksum pin:

```bash
cd web-prototype && PUBLIC_BUCKET=<project>-fighter-assets pnpm assets:publish
```

Commit `config/characters.json` and `config/baked-assets.json` together.
Objects are keyed by content hash, so publishing is additive and every past
commit stays reproducible. Deployment (Cloud Run, Cloud Run job worker,
Cloudflare edge cache) is one script; see
[`web-prototype/infra/README.md`](web-prototype/infra/README.md).

## Game-derived inputs

A few generator inputs are captured from the game itself rather than
authored, and every one of them can be rebuilt from your own ROM:

| Files | What they are | Rebuilt by |
|---|---|---|
| `skels/*.skel`, `skels/fk*-all.log`, `skels/parts/*.json` | The twelve fighters' rest-pose skeletons and part geometry, which the converter fits generated meshes onto | `derive_skeletons.py` (runs the engine) |
| `assets/css-font/portraits`, `assets/css-font/locked` | Character-select portrait tiles, fire slot, question mark, shadows | `derive_from_rom.py` |
| `web-prototype/visual/assets/ui_refs/` | Tile and name sprites, stock icon, emblem sheet, and the glyph atlases the UI packer composes names from | `derive_from_rom.py` (four letters need `--skeletons`) |
| `eval/announcer_conditioning_corrected/` | The announcer lines the voice clone is conditioned on, rendered at in-game pitch | `derive_from_rom.py` |
| `stone-tile-investigation/source-*` | The character-select stone texture | `derive_from_rom.py` |

Hand-authored files next to them (`skels/*.profile.json`, `skels/VALIDATION.md`,
`assets/css-font/letters`) are not derived. `skels/reference/mario.skel` is a
legacy capture from an older engine build that `texture_check.py` still reads;
it is the one file the scripts report as LEGACY instead of reproducing.

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

This derives everything into a temporary directory and prints one line per
file: `IDENTICAL`, `DIFFERS` with a one-line reason (pixel count, which joints
moved), or `LEGACY`. It exits non-zero on any difference. `--skeletons` boots
`BattleShip/build-us/BattleShip` thirteen times (once per fighter with
`SSB64_DUMP_SKELETON`, once on the character-select screen with
`SSB64_DUMP_SPRITES`); a game window opens and closes each time, about ten
seconds per launch. Leave it off to check only the archive-based files.

### Regenerate

```bash
python3 tools/derive_from_rom.py --skeletons
```

Without `--verify` the scripts write straight into the tracked paths. Use
`--out DIR` to write a mirror of the repo layout somewhere else instead. Other
useful forms:

```bash
python3 tools/derive_skeletons.py --verify --fighters samus,link
```

```bash
python3 tools/derive_skeletons.py --verify --from-logs skels
```

The first limits the engine runs to named fighters (names or fkind numbers).
The second skips the engine and re-derives from the committed raw dump logs,
which checks the parsing and the profile-map transform without a ROM. Pass
`--build-dir` to either script to use a different native build.

The `dl=` field in the skeleton dumps is a host memory address the engine
prints; the scripts normalize it to its stable low bits so two launches
produce identical files. The only consumer tests it for zero.

## More documentation

- `EVAL.md`: the mesh-generation and skinning evaluation harness and its
  history of experiments.
- `ANNOUNCER.md`: announcer voice generation and the MiniMax clone.
- `docs/site-visual-assets.md`: how the site's 3D console, cartridge, CRT
  intro, and other props were made.
- `web-prototype/docs/production-architecture.md`: the hosted generation
  service (Firestore job protocol, retries, abuse controls).
- `BattleShip/docs/`: engine internals, the web harness, controller ports,
  and in-browser ROM extraction.
