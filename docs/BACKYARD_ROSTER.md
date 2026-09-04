# Backyard Designers × OpenSmash — DesignCrit

Fork of [turtlesoupy/opensmash](https://github.com/turtlesoupy/opensmash) reskinned
around [backyarddesigners.club](https://backyarddesigners.club) — 223 draftable
designers as Smash fighters.

Upstream: `https://github.com/Jaksenc/opensmash` (fork) — this branch: `backyard-roster-v1`.

## Status: fully staged locally (12/12 in baked roster, playable brawler)

- [x] Simplified setup: `GET /api/backyard-starter` + `GET /backyard-refs/*`
  work with no ROM, engine, or keys. `pnpm dev:safe` boots.
- [x] Movesets/balance: `POSITION_CLASSES` in `server/roster.js`
  (Leader=captain, Product=rushdown, Engineer=zoner, Brand=tricky, Web=control,
  Wildcard=heavy) + `assignPositionClasses()` + tests.
- [x] UI/branding: `src/BackyardDraftBoard.jsx` + `src/backyard.css` — position
  filters, salary cap tracker (400k), class/base badges, scout links,
  click-to-announce, generated sprites with ref fallback.
- [x] Sprites (no keys, no ROM): `scripts/backyard_sprites.py` builds real
  `.osbui` packs (portrait + caption, panel name, stock icon, emblem) for all
  12; `scripts/synth_ui_refs.py` stands in the 10 ROM-derived panel dumps.
- [x] Statues (no Tripo, no ROM): `scripts/backyard_statues.py` authors real
  single-target `.osb6` bundles — procedural chibi (~132 tris), backyard-textured
  atlas, rigid single-joint rig. Verified by the repo's own preview parser
  (`shared/backyard-statues.test.js`, 13/13) plus texel spot checks. They are
  RIGID preview bodies, not animated fighters: in-engine motion needs the
  ROM skeletons + Tripo rig from `run_character.py`.
- [x] Announcer (no Fal): `scripts/backyard_announcer.py` renders all 12
  `announcer.wav` clips with macOS `say` (Daniel, 16-bit PCM 22kHz).
- [x] Staged: all 12 appended to `config/characters.json` → baked roster is
  **12/12 with ui+voice true**, served via standard `/character-assets/` and
  `/api/characters` (verified live).
- [x] Playable today: `src/BackyardBrawl.jsx` — canvas platform fighter
  (A/D move, W double-jump, J jab, K class special, Esc), % damage, blast KOs,
  3 stocks, CPU AI, announcer intro. "Brawl ↗" on any draft card.
- [x] Cartridge banner: no-ROM visitors get "◼ No cartridge" + Play Backyard
  Brawl (scrolls to board) + Insert cartridge (opens ROM handoff) instead of
  an error wall; ROM owners see "● Cartridge in". Click-verified headless.
- Pre-existing failure (not ours): `og-studio.test.js` "transformed fighter hit
  testing" fails on clean `e38b3b9` too.

## Build everything locally (no keys, no ROM)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/fetch_backyard_roster.py --starter-only
.venv/bin/python scripts/synth_ui_refs.py
.venv/bin/python scripts/backyard_sprites.py   # .osbui packs
.venv/bin/python scripts/backyard_statues.py   # .osb6 statues
python3 scripts/backyard_announcer.py          # announcer.wav
cd web-prototype && pnpm install && pnpm backyard:dev
```

Still needs your keys/ROM for the real thing: Tripo mesh + Fal voice
(`run_character.py --force-stage mesh|voice`), NTSC-U ROM + `BattleShip`
build to boot the N64 engine itself.

## Starter 12 (v1 scope)

One fighter per Smash skeleton (12/12), covering all 6 backyard positions.
Cost to generate all 12 via full pipeline: ~12 × $0.65 ≈ **$7.80**.

| # | Designer | Backyard position / epithet | Smash base | Why this base | Short | Emblem (1-color stencil) |
|---|----------|----------------------------|------------|---------------|-------|--------------------------|
| 1 | Ridd (@ridd_design) | Design Leader / THE COMMISSIONER | mario | all-rounder commissioner | RIDD | a brown leather football |
| 2 | Tommy Geoco (@designertom) | Design Leader / THE LOREKEEPER | luigi | lanky documentarian, luigi parallel | LORE | a vintage film camera |
| 3 | Rauno Freiberg (@raunofreiberg) | Product / THE DETAILER | fox | fast, pixel-precise rushdown | RAUNO | a pixel cursor arrow |
| 4 | Pablo Stanley (@pablostanley) | Product / THE ILLUSTRATOR | kirby | cute, summons Humaaans minions | PABLO | a paintbrush |
| 5 | Julie Zhuo (@joulee) | Design Leader / LOOKING GLASS | samus | systematic tactician, ranged | ZHUO | an open book with glasses |
| 6 | Katie Dill (@lil_dill) | Design Leader / THE PILOT | captain | falcon-speed checkout flows | DILL | a striped checkout receipt |
| 7 | Mery Kaftar (@merycodes) | Design Engineer / DRAG HANDLE | link | gadget zoner, nav-resize hooks | MERY | a drag handle with arrows |
| 8 | Jhey Tompkins (@jh3yy) | Design Engineer / THE SHOWMAN | pikachu | electric demo energy | JHEY | a lightning bolt plug |
| 9 | Phi Hoang (@apostraphi) | Brand / THE FIGURE-OUTER | purin | sing = brand-reveal moment | PHI | a perplexity-style spark |
| 10 | Tobias van Schneider (@vanschneider) | Brand / THE GARDENER | ness | psychic garden PK powers | TOBIAS | a small potted seedling |
| 11 | Rob Hope (@robhope) | Web / ABOVE THE FOLD | yoshi | egg = single-page capsule | ROB | a single folded web page |
| 12 | dára sobaloju (@darasoba) | Wildcard / #1 beamer | donkey | heavy with beam cannon | DARA | a glowing beam cannon |

Position coverage: Leader 3, Product 2, Engineer 2, Brand 2, Web 1, Wildcard 1 + 2 captains.
Full 223 list: `backyard/roster.json` (via `scripts/fetch_backyard_roster.py`).

## Generate one

```bash
cp .env.example .env  # fill OPENAI_API_KEY, TRIPO_API_KEY, FAL_KEY, MINIMAX_ANNOUNCER_VOICE_ID
python3 scripts/fetch_backyard_roster.py --starter-only
python3 pipeline/run_character.py "Rauno Freiberg" \
  --photo backyard/refs/raunofreiberg_action.webp \
  --short RAUNO --emblem "a pixel cursor arrow" \
  --notes "the detailer, vercel designer, obsessive micro-craft, sharp speedy fox energy" \
  --variants all
python3 pipeline/baked_roster.py raunofreiberg
```

Batch all 12: `python3 scripts/batch_characters.py backyard/starter12-names.txt --workers 3`
Retry a stage: `--force-stage tpose|mesh|convert|portrait|stock|emblem|ui|voice`.
Art inputs: `-action.webp` (full-body, best for `--photo`) + `-thumb.webp` (face ref).
Pipeline constraints (from `pipeline/expand_character.py`): empty hands, fitted
clothes, no capes/skirts/hanging props, matte non-black palette, mouth closed.

## Improvements roadmap (agreed scope)

1. **New UI / branding** — Backyard club theme: draft-board character select,
   position badges (Leader/Product/Engineer/Brand/Web/Wildcard), follower-salary
   as power value, chunky-cartoon CSS to match `/roster-art/` style.
   Entry: `web-prototype/src/*`, `web-prototype/config/backyard-starter.json`.
2. **New movesets / balance** — position-based classes, not 1:1 clones:
   Engineer = trap/zoner (Link/Samus), Product = rushdown (Fox/Captain),
   Brand = status/sleep (Purin/Ness), Leader = all-rounder buffs (Mario/Luigi),
   Web = capsule/egg control (Yoshi), Wildcard = heavy (Donkey/Kirby).
   Entry: `web-prototype/server/roster.js` (`preferredBases` + weights).
3. **Simplified setup** — DONE: `backyard/` one-command fetch, `pnpm dev:safe` default
   (no paid jobs), committed `backyard/starter12.json`, `/api/backyard-starter`
   + `/backyard-refs/` + `/backyard-art/` serve everything with no ROM/keys,
   and Backyard Brawl is playable in the browser today. ROM still required
   for the N64 engine itself (NTSC-U v1.0, SHA-1 `e2929e10…`); engine
   lives in sibling `BattleShip/` fork (not in this repo).

## Files added this branch

- `scripts/fetch_backyard_roster.py` — roster pull + ref download + starter JSON
- `scripts/mock_backyard_fighter.py` — offline character.json/portrait dry-run
- `scripts/backyard_sprites.py` — local .osbui packs from backyard art
- `scripts/backyard_statues.py` — procedural statue .osb6 bundles
- `scripts/backyard_announcer.py` — local announcer.wav via macOS `say`
- `scripts/synth_ui_refs.py` — stand-in panel-name dumps (local only)
- `web-prototype/config/backyard-starter.json` — 12-fighter draft roster
- `web-prototype/src/BackyardDraftBoard.jsx` + `backyard.css` — draft board
- `web-prototype/src/BackyardBrawl.jsx` — playable canvas brawler
- `web-prototype/shared/backyard-statues.test.js` — bundle verification
- `web-prototype/server/roster.js` — POSITION_CLASSES + assignPositionClasses
- `docs/BACKYARD_ROSTER.md` — this file
- `backyard/` (gitignored except JSON/txt) — refs + names, fetched locally
