# Backyard Designers × OpenSmash — DesignCrit

Fork of [turtlesoupy/opensmash](https://github.com/turtlesoupy/opensmash) reskinned
around [backyarddesigners.club](https://backyarddesigners.club) — 223 draftable
designers as Smash fighters.

Upstream: `https://github.com/Jaksenc/opensmash` (fork) — this branch: `backyard-roster-v1`.

## Status: implemented (art-only playable, 3D pending keys/ROM)

- [x] Simplified setup: `GET /api/backyard-starter` + `GET /backyard-refs/*`
  work with no ROM, engine, or keys. `pnpm dev:safe` boots, baked roster 0,
  draft board 12/12. Try: `pnpm backyard:fetch && pnpm backyard:mock`.
- [x] Movesets/balance: `POSITION_CLASSES` in `server/roster.js`
  (Leader=captain, Product=rushdown, Engineer=zoner, Brand=tricky, Web=control,
  Wildcard=heavy) + `assignPositionClasses()` + 2 new tests (12/12 roster tests pass).
- [x] UI/branding: `src/BackyardDraftBoard.jsx` + `src/backyard.css` wired into
  `App.jsx` above character select — position filters, salary cap tracker
  (400k), class/base badges, scout links. `pnpm build` green.
- [x] Fighters dry-run: `scripts/mock_backyard_fighter.py --all` created
  `play/ui/<slug>/{character.json,cost.json,portrait_*.png,announcer.txt}` for
  all 12. Real `.osb6`/`.osbui`/`announcer.wav` need `.env` keys + NTSC-U ROM +
  `BattleShip` build — see "Generate one" below.
- Pre-existing failure (not ours): `og-studio.test.js` "transformed fighter hit
  testing" fails on clean `e38b3b9` too.

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
3. **Simplified setup** — `backyard/` one-command fetch, `pnpm dev:safe` default
   (no paid jobs), committed `backyard/starter12.json` so roster works without
   ROM/API keys ( Lia: art-only mode reusing `-thumb.webp` as portraits).
   ROM still required for real matches (NTSC-U v1.0, SHA-1 `e2929e10…`); engine
   lives in sibling `BattleShip/` fork (not in this repo).

## Files added this branch

- `scripts/fetch_backyard_roster.py` — roster pull + ref download + starter JSON
- `web-prototype/config/backyard-starter.json` — 12-fighter draft roster
- `docs/BACKYARD_ROSTER.md` — this file
- `backyard/` (gitignored except JSON/txt) — refs + names, fetched locally
