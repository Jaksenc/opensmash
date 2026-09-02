# Smash Weights

## Repository layout

- `web-prototype/` — the production React website, Node server, deployment
  configuration, and canonical browser assets under `visual/`
- `pipeline/` — directly executable Python generation and evaluation tools
- `scripts/` — batch sweep drivers
- `play/` — git-ignored local fighter-generation workspace; production runtime
  files are content-addressed in GCS and pinned by
  `web-prototype/config/baked-assets.json`
- `skels/` — canonical skeletons, profiles, and extracted part data
- `eval/` — evaluation code, fixtures, and generated results
- `artifacts/experiments/` — historical generated models, atlases, bundles, and reports
- `tools/` — maintenance, generation, and verification utilities

Run the website from its app directory:

```bash
cd web-prototype
pnpm install
pnpm dev
```

Then open `http://127.0.0.1:4174/`. See `web-prototype/README.md` for the
production build, fighter worker, authentication, and deployment flows.

## Retro cartridge

`web-prototype/visual/assets/n64-cartridge-tripo.glb` is a Tripo P1 multiview model generated from
front, side, and back references. It is used by the centered cartridge
control in the production visual runtime and rendered inside
the same low-resolution Three.js post-process as the glove, including the
posterized palette, dithered alpha edge, and dark one-texel outline.

The original procedural fallback can be rebuilt with:

```bash
blender --background --python tools/build_cartridge_model.py
```

## Recovered N64 console + fitted cartridge interaction

`assets/n64-console-sketchfab-recovered.glb` is the recovered 718-triangle
viewer model with embedded diffuse, normal, and AO maps from NeoZeroo's
original Sketchfab upload.
The archival recovery remains untouched. Normalize its axes, scale, and texture
size for the site with:

```bash
blender --background --python tools/prepare_sketchfab_console.py
```

`web-prototype/visual/assets/hybrid-four-port-console-fitted.glb` preserves the recovered shell,
four ports, top switches, badge, and cartridge slot. A small flush cover adds
`FUN` light pipes, and a `CartridgeSnapAnchor` node drives the site interaction.
Rebuild that derived interaction asset with:

```bash
blender --background --python tools/build_console_cartridge_system.py
```

The cartridge is scaled to 44% of the console width. The receiver is derived
from the cartridge bounds and adds 0.006 units of clearance per side. It begins
centered in the open space between the top of the viewport and the console;
its idle depth sits closer to the camera. Pressing it springs the cartridge back
onto the console's drag plane and immediately gives the console a small upward
tilt. Dragging downward smoothly continues that tilt toward the cartridge while
rotating the cartridge into its entry angle well before it reaches the slot.
The console is treated as a fixed rounded rigid collider and the dragged
cartridge as a spring-driven movable rigid body. Off-axis approaches resolve
against the console's top, shoulders, rounded corners, and sides with normal
impulse, light restitution, and tangential friction. Only a narrow capture
throat around the cartridge centerline is open. Once the cartridge body reaches
the visibly seated point inside that throat, it clamps to the slot mouth and
finishes with a short non-overshooting insertion animation; high-speed pulls
cannot tunnel through the console. Releasing any incomplete drag always
springs it directly from the release point to the upper resting pose with a
small settling overshoot, without an intermediate slot or center waypoint.
Inside a tapered cone above the slot,
a progressive horizontal attraction stays gentle high up and grows assertive
near the opening; outside that cone there is no positional assistance. Approach
assistance also rotates the cartridge into the authored slot angle and eases it
onto the slot's exact depth plane while the console tilts slightly upward to
meet it. Once the cartridge is fully seated, the cartridge and console animate
off the bottom of the viewport. The presenter credit fades in first, followed
by the rest of the site two seconds later. Releasing the free cartridge launches
a fast clockwise Y-axis spring that leaves its label facing forward; inserting
it requires dragging it into the console slot. The hand mesh is always rendered
above both pieces of hardware.

The default runtime shader uses 2× pixels, 12 color steps, 50% posterization,
full edge dither, a 70%-strength 1px `#383838` outline, and display gamma 2.50.
The tuning controls remain part of the page but are hidden from the final UI.

## Tripo CRT intro screen

`assets/tripo-crt-tv.glb` is a 10k-face-target, geometry-only Tripo v3.0
image-to-model result generated from the supplied Trinitron reference. The
optional cartridge intro gives the cabinet an authored charcoal material and
places the local `assets/intro-crt.mp4` clip on a segmented, physically curved
screen. The default route loads the character-grid site directly and plays the
same clip in the 4:3 video container at the top of the page.
Its dedicated Three.js shader adds barrel distortion, scanlines, an RGB
phosphor mask, chromatic separation, a rolling brightness band, vignette,
flicker, and fine analog noise. The optimized 1280×960 H.264 clip preserves the
original 4:3 framing while reducing the browser payload from 108 MB to about
7.4 MB.

Append `?intro=cartridge` to the local URL to preview the preserved cartridge
insertion experience. The default URL opens the running main screen directly.
`#skipboot` can still be added to the cartridge URL to bypass its interaction.

The full browser viewport uses a 199X-inspired two-stage treatment: a backdrop
pass adds the slight composite softness, color density, and pixel blending of
the original preset's color/NTSC stages, then `crt-viewport.js` adds the tube
edge, vignette, visible raster lines, RGB aperture grille, rolling luminance,
flicker, and analog noise above every page layer. Add `?crt=off` to compare the
page without the viewport effect, or `?crt=soft` for a restrained version of
the default exaggerated preset.

## Mesh generation

Meshy and Tripo are configured through the git-ignored `.env` file. The mesh
generator is dependency-free and uses Python 3's standard library.

Validate both API connections without spending generation credits:

```bash
python3 tools/generate_mesh.py check
```

Generate an untextured GLB (the cheaper geometry-only path):

```bash
python3 tools/generate_mesh.py generate \
  --provider meshy \
  --prompt "a low-poly fighting-game arena platform"
```

```bash
python3 tools/generate_mesh.py generate \
  --provider tripo \
  --prompt "a low-poly fighting-game arena platform"
```

Generate from ordered front, left, back, and right reference images with
Tripo's multiview model:

```bash
python3 tools/generate_mesh.py generate-multiview \
  --front front.png \
  --left left.png \
  --back back.png \
  --right right.png \
  --target-polycount 8000 \
  --name referenced-model.glb
```

Generate from a single concept or product reference image with Tripo:

```bash
python3 tools/generate_mesh.py generate-image \
  --image concept.png \
  --textured \
  --target-polycount 15000 \
  --name referenced-model.glb
```

Add `--textured` for textures and PBR maps. Meshy accepts optional texture
guidance with `--texture-prompt`; either provider accepts `--target-polycount`.
For example:

```bash
python3 tools/generate_mesh.py generate \
  --provider meshy \
  --prompt "a chunky red arcade joystick, centered, no background" \
  --textured \
  --texture-prompt "red enamel, brushed steel base, subtle wear" \
  --target-polycount 12000
```

Finished models are downloaded to `web-prototype/visual/assets/generated/` by
default. This folder is git-ignored because generated GLBs can be large. Use `--output-dir` or
`--name` to change the destination. Run the CLI with `--help` for all options.

Generation consumes provider credits. `--textured` may consume additional
credits, and Meshy's textured flow runs a preview task followed by a refine task.

## Wikipedia people seed

Build a popularity-ranked, upload-ready people list from Wikipedia pageviews
and Wikidata's human metadata. The default ordering is pure all-Wikipedia
Wikidata PageRank, favoring durable encyclopedic centrality over short-lived
attention spikes. QRank's rolling twelve-month pageview total remains available
for an optional geometric rank blend. Monthly English top-page lists supply the
candidate pool; they do not supply the final score:

```bash
python3 tools/build_wikipedia_people_seed.py --limit 500
```

The size is deliberately tunable; for a larger pool, use `--limit 2000` with
the same ranking and eligibility rules. The default output is
`wikipedia-people-<limit>.txt`, one name per line. Add `--details-output` for a
scored review CSV, `--exclude`/`--exclude-file` for editorial exclusions, or
increase `--months` and `--oversample` if a very large target exhausts the
eligible candidate pool. The weights pipeline is assumed to supply imagery;
`--require-image` is available as an optional stricter filter. API responses
and the ranking snapshots are cached under `.cache/`. Use `--pagerank-weight 0`
for pure QRank or `--pagerank-weight 0.35` for the previous 65/35 blend.
`--qrank-file` and
`--pagerank-file` accept local snapshots; the corresponding URL options update
the default sources.

The generator also applies `config/wikipedia-roster-inclusions.txt`. Those
names are guaranteed a slot within the exact `--limit`, displacing the lowest
ranked non-inclusions when necessary. Use `--include`/`--include-file` for
additional names or `--no-default-inclusions` to audit pure ranking output.
If a named person has no standalone human Wikipedia/Wikidata page, the literal
name is retained with deterministic local metadata and a zero popularity score.

The generator applies `config/wikipedia-roster-exclusions.txt` by default and
replaces excluded entries so `--limit` remains exact. The human-review rules
behind that list are documented in `docs/character-roster-editorial-policy.md`.
Use `--no-default-exclusions` only for auditing the unfiltered source pool.
