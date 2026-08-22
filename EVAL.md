# Mesh generation strategy eval — Napoleon Bonaparte test (2026-08-07)

| Strategy | Result | Verdict |
|---|---|---|
| A: text → Meshy text-to-3D | Good likeness, **ignored T-pose** (hands clasped), untextured preview | ✗ pose control unreliable |
| B1: GPT-Image-2 T-pose sheet → Meshy image-to-3D | Perfect T-pose, fully textured, clean geometry | ✓ **WINNER** |
| B2: Gemini 3.1 Flash Image → Meshy image-to-3D | Good, chunkier N64 style, but bent arms + podium reconstructed into mesh | ~ usable with prompt fixes |

Prompt rules learned: demand "strict T-pose, arms perfectly horizontal", "plain white background", "no floor, no podium, no pedestal", "full body centered". Image model quality transfers directly to mesh quality.

Files: napoleon-{A,B1,B2}*.{glb,png}; task ids in this dir's history. ~20 Meshy credits + ~$0.15 total.

# Mario-match eval v2 (2026-08-17)

Pipeline: Gemini flash-image T-pose (gemini-3.1-flash-image; OpenAI blocks
Mario-likeness at output moderation) -> Meshy img3d (4k polys) -> Meshy rig
-> convert_rigged.py (v10+: vanilla part-profile conform + triad twist
control + foot toe-triads + mirror-pair symmetrize + crotch fill + shallow
shade ramp/vibrance) -> OSB3 -> in-game injection.

Reproducible in-game eval: make_replay.py (scripted mirrored move tour,
both players human) + run_eval.py (BOOT_BATTLE=0,0,4,0 + REPLAY_PLAY +
Metal-backend screenshots) + compare_runs.py / crop_fighters.py.
Ground truth: identical replay without injection; P2 in-frame is a
jitter-free vanilla reference.

Key data: vanilla-mario-parts.json = per-joint vanilla Mario vertices
dumped by the game (SSB64_DUMP_SKELETON=0, MESHV lines in ssb64.log).

Best bundle so far: plumber3.osb (from plumber3-tpose.png, closed mouth).
Known weak spots: crouch (crotch gap, flat splayed shoes), eye texture
smear at grazing angles, glove shard edges in fast poses.

## Verifier score history (fresh-eyes agent, 34-pair move tour)
- r1 plumber3 baseline conform: 6/10 (shred in tumble, no lighting, palette off)
- r2 +reskin+caps+lighting+recolor: 7/10 (size too big, torso color blocking)
- r3 plumber5 +size trim+flash attempt: 6.5/10 (foot shards, glove tint, M smear)
- r4 geodesic reskin + all-hard-cuts: 4/10 REGRESSION (reverted)
- r5 restored best recipe: 6.5/10

Final bundle: plumber5.osb. Remaining defect classes (root causes known):
1. Sliver shards in crouch/tumble/taunt: LBS-authored blend geometry rendered
   part-rigid; Meshy weight bleed on chibi bodies puts arm weights on waist
   verts (adjacent verts land in different bone maps -> long authored tris).
   Geodesic reassignment failed (capsules overlap on chibi). Next idea:
   author each part's verts through its OWN map (not the LBS blend) and
   accept rest-pose seams, or diffuse assignments in UV space.
2. Damage/invincibility flash not tinting the model: colanim swaps the
   fighter combiner; inheriting it renders black on non-flash frames.
   Needs understanding of the colanim combiner program (decomp ftcolanim).
3. Crouch depth reads shallow: torso volume distribution, cosmetic.

## Lighting parity solved (2026-08-18)
Two mechanisms, both now handled in ftport.c osbBuildPartDL3 (lit/OSB4 path):
1. Vanilla part colors ARE their light colors (material-tinted LIGHT_1 via
   the mobj pipeline). Inheriting them multiplied our textures by the part
   tint (~color^2, dark+oversaturated). Fix: own neutral lights
   (gdSPDefLights1 145 ambient / 255 white key).
2. Stage tint + colanim flashes ride the fighter pipeline's 2-CYCLE +
   G_RM_FOG_PRIM_A render state with the wash color as fog/env color
   (ftdisplaymain.c:1219+). Our DL used to force 1-cycle OPA — killing the
   wash. Fix: inherit cycle/render mode, combiner (MODULATEIA, PASS2).
Verifier r9 confirms lighting response now matches vanilla.

Scores: r7 7 (Tripo) -> r8 6.5 (brightness exposed shreds) -> r9 7
(lighting fixed). Remaining to 9: pelvis/thigh crease shards in standing
poses (reskin band normals/weights at crotch), hit-react torso garble,
crouch depth, SM64-vs-Smash64 identity flavor (chest color blocking,
big yellow buttons, black mustache — source-image or atlas-level fixes).

## Active plan (2026-08-18, autonomous push to 9+)
1. Tour facing fix: fighters cross in approach; P2 ends back-turned (user
   noticed). make_replay: shorter approach + face-tap segment; MUST
   recapture BOTH runs (final-vanilla reference too) with the new replay.
2. Crotch crease/shard fix hypothesis: authored normals are rotated by
   each vert's DOMINANT part Q (vnormal), so seam-adjacent verts shade
   discontinuously -> dark triangular streaks. Fix: recompute smooth
   welded normals from the AUTHORED (world) mesh after LBS, replacing
   the per-part rotated ones.
3. Identity: regen source image (plumber6): red chest visible, LARGE
   yellow buttons mid-chest, narrow blue bib, jet-black compact mustache,
   brown shoes, smaller cap -> tripo.py upload/img3d/rig -> convert
   --reskin --mild-color + recolor --tripo.
4. Verifier prompt already requires category critique + rationale — keep.
5. Champion so far: tripo-champion.osb at 7/10 (r9).

## Autonomous push round 10-14 (2026-08-18/19)
- r10 (tripo v8, fog+neutral lights): 7.5 — new peak; mechanics "essentially
  perfect", lighting response confirmed matching.
- Same-facing tour (mirror approach only) per user feedback; P1 = LEFT.
- plumber6 (black mustache, pale skin source) via Tripo; r11 (old pairs): 7,
  r13 (same-facing): 7 — top levers named: torso red-chest blocking (+1-1.5),
  crotch cap-UV tear (fixed: cap centroid UV now samples a loop vertex),
  thicker legs (floors 1.05).
- --redchest pass added: finds button height from yellow texels, repaints
  blue->red between buttons and collar (band_hi = btn+0.17H; unbounded band
  turned the EYES red). Skin warm-tan (not pale), shoes maroon.
- Candidate: p6-champion.osb (r14 verdict pending at context handoff).

## Vanilla-guided source (2026-08-19) — the sculpt/style breakthrough lever
r14 stayed 7: verifiers cap on "visibly a different sculpt/style", immune
to color surgery. New approach: gen.py --ref support feeds a REAL in-game
vanilla Mario screenshot crop (vanilla-ref-crop.png) to Gemini, prompt
demands exact preservation -> vanilla-guided-tpose.png is essentially the
true N64 model (proportions, facets, blocky mustache, blocking). Tripo
task 3e9352a4-f0be-4614-a892-1c3cf7ffbb2b (mesh) -> rig -> convert with
--reskin --mild-color ONLY (skip --redchest: blocking already right;
recolor --tripo maybe skip too — colors already vanilla). Then capture
KEY=400,440,455,517,555,640,710,780,800,850,865,930,945,1010,1045,1090,
1120,1133,1148,1170,1190,1225,1260,1320,1345,1425,1485,1535 via
run_eval.py, pairs vs ref4-vanilla (P1=LEFT, same-facing), verify.

## Vanilla-guided build landed (2026-08-18)
vg-rigged.glb -> vg.osb (--reskin --mild-color only; NO recolor needed —
colors already vanilla). Conform scales all ~1.0-1.25 (sculpt matches
vanilla by construction). In-game close-up: flat-shaded facets, blocky
black mustache, cream skin, red chest + button, squat proportions — first
build that reads as the same game's art style. r15 verdict pending.
Tripo rig URLs EXPIRE within minutes of success — poll+download must be
one foreground command (see the失败ed background waiters).

## Rigid-consistent overlap (2026-08-18) — the discontinuity root-cause fix
User diagnosis confirmed: holes/discontinuity come from the INJECTION
model, not the upstream mesh. Provider rigs are smooth multi-bone LBS
(holes impossible); the game renders ONE RIGID transform per joint, so
chopped parts must separate at bent joints. Vanilla models fix it by
authoring parts as closed volumes OVERLAPPING through joints.
Implemented in convert_rigged:每 part = majority tris + extension band
(all verts >= EXT_W 0.10 weight in the part), and each part's verts are
authored via RESTRICTED LBS (part_world: only the part's own bones,
renormalized) so extensions move rigidly with the part and interpenetrate
neighbors under rotation. Crouch renders as solid volumes now — no holes,
no slivers. Prior blend-copies failed because copies were authored at
FULL-LBS positions (slivers under rotation).
Candidate: vg2-champion.osb (vanilla-guided2 source + overlap authoring).
Known nits: maroon shoe-hem fringes (foot extension), r16 pending.

## CPU SKINNING LANDS (2026-08-18) — discontinuity class eliminated
User asked "is the problem that the game doesn't use skeletal animation?"
Precisely: the game HAS skeletal animation but NOT skinned deformation
(one rigid DL per joint). Solution: TRUE CPU skinning in the port.
- OSB5 format (--binary5): whole un-chopped mesh, spawn-world f32 verts,
  4x (joint,weight) per vert, uv/normals; bundle json carries "skinned".
- ftport.c: osb5_load captures spawn inverse-bind per vert per influence,
  builds ONE DL on joint 0 (TopN) with 30-vert windows + a window remap
  table; blanks all other joint DLs. port_osb5_skin_update (hooked in
  ftMainProcParams next to port_dump_frame) recomputes every vertex by
  full LBS from live joint matrices each tick; port_osb5_copy_windows
  copies into the window Vtx arrays. Fog/neutral-light state as OSB4.
- In-game result: provider-grade smooth deformation; idle+crouch have NO
  seams/holes/fringes. Champion: skinned-champion.osb (= vg2-skinned.osb,
  from vanilla-guided2 source). Remaining known nit: red texture seam at
  inner thigh (atlas), face expression swaps don't exist.
- r17 verification pending at handoff.

## r18/r19 (2026-08-18)
- r18 (vg3-skinned): 7.5 — FIRST fully clean glitch report (no tears/
  shards/artifacts anywhere), animation flawless, lighting correct.
  Remaining: silhouette slimmer than vanilla, gloves/feet small, chest
  blue-dominant, ears/back-hair missing, mustache edge noise, no
  expression swaps (would need face texture-part swap hookup).
- Tour: fireball moved LAST with P2 shield override (user: fireball hit
  flipped facings mid-tour). New marks; KEY frames updated in run cmds.
- Conform: SPAN_TRIM 0.94->1.02 (was shrinking vs vanilla), leg floors
  1.12, gloves cap 1.45, feet 1.0-1.5. Rebuilt vg3-skinned = champion.
- r19 pending on the chunkier build + fixed tour.

## r20 build (2026-08-18)
- Cap-sail fix: OSB5 emitter snaps ALL verts within 0.30*H of the Head
  joint (and above neck_y+0.01H) to 100% Head weight (218 verts) — the
  sail was the LBS membrane between 100%-Head and 100%-chest verts in
  head-down poses (utilt/usmash). Close-up at 675 confirms cap+hair now
  move rigidly with the head.
- Plus: --redchest (43974 px blue->red at button band) and --bluelegs
  (52733 px) atlas repaints on vg3-rigged.glb; chunkier conform.
- Champion updated: skinned-champion.osb = vg3-skinned.osb (this build).
- r20 verifier running on sk9-injected vs ref5-vanilla, 29 pairs.

## r20 -> r21 (2026-08-18)
- r20: 7/10. Two dominant defects: (1) torso reads BLUE jumpsuit — the
  old --redchest band (all-verts-in-band) only painted a collar sliver;
  (2) red "scarf flap"/tuck "sail" = the model's back HAIR is painted
  RED in the source texture (205 head-boned red verts at chest height).
- Fixes:
  * --redchest rewritten: centroid-in-band chest tris (part 6), band
    btn_y-0.05H..+0.17H, wraps sides/back; front-central bib below the
    buttons excluded (stays blue). 111k px painted. In-game: red shirt
    over blue bib, near-vanilla read.
  * --brownhair (new): red texels on lower-head tris (below eye level,
    excluding front brim; NOTE model faces +X in bind space, not +Z)
    -> hair brown. Kills the scarf flap.
  * bluelegs crotch zone y_lo 0.45H -> 0.38H (stop clobbering redchest).
  * cap claim radius 0.30H -> 0.42H + skip ForeArm/Hand provider bones.
  * cap shrinkwrap: head-rigid verts beyond 1.12*median head radius
    pulled radially in (except +x front brim). Payload verified: ALL
    above-neck verts 100% Head — remaining tuck read is cap COVERAGE
    (bare temple/side skin + face occupies more of the head sphere than
    vanilla), NOT a skinning membrane.
  * --capfix (paint top-band head skin -> cap red) REGRESSED: shared UV
    islands streak red spikes across the face in tuck; sideburn pinked
    in idle. Reverted — do not retry as flat texel repaint.
- r21 running (sk15-injected vs ref5-vanilla).

## r21/r22 (2026-08-18) — two-axis rubric
- r21: 6.5 — cap shrinkwrap REGRESSED tuck from smooth sheet to spiky
  shards (radial clamp with spared neighbors = jagged edge). Gated off
  behind --shrinkwrap; champion rebuilt without it.
- r22 (same build minus shrinkwrap), NEW two-axis verifier per user:
  * Likeness to vanilla: 7.5/10 (ties r18 best). Steady-state tells:
    darker striped overalls, buttons at collar not on bib, slim legs,
    open-mouth blob close-up; glitch: tuck-pose red cap sheet 675/895.
  * Pipeline execution (source image = design intent): 7/10. Geometry/
    lighting/deformation near-flawless (27/29 clean); dinged for
    texture drift vs source (buttons moved, striping, zigzag hem, open
    mouth — mostly Tripo texture-bake drift, judge counts it as
    conversion) and the tuck flexion failure.
- Conclusion: remaining likeness gap is ~source/provider fidelity
  (texture drift + cap coverage + face sculpt), not conversion
  robustness. Options to 9: cleaner source image / provider texture
  pass (repaint atlas from source image), tuck-pose head geometry.

## --vanillaflat (2026-08-18, user: "overalls are pure blue in game")
- New pass replaces --redchest/--bluelegs: rasterizes a per-texel 3D
  position + part map into the atlas, then paints FLAT vanilla colors
  with pixel-straight boundaries: flat blue overalls+bib (palette
  sampled from vanilla-ref-crop, V*1.25), flat red shirt/arms wrapping
  sides+back above waist, gold buttons at bib corners (vanilla spot,
  Tripo collar buttons erased), flat gloves/shoes, shoe/leg cut at
  y=min+0.105H. Strap-preserve heuristic failed (source chest all blue)
  — dropped. Build: --reskin --mild-color --brownhair --vanillaflat.
- In-game 1225: dramatically closer to vanilla; minor blue jag on left
  boot top (posmap texel overwrite at part-shared texels). Champion
  updated. Full r23 verify round still to run.

## r24 (2026-08-18) — vg4, GENERAL-ONLY pipeline
- vg4 = new source-image template (flat cel colors, closed mouth, snug
  cap, ears, chunky) -> Tripo -> convert --reskin --mild-color ONLY.
- NEW general converter fix: facing auto-detect (toes-point-forward dot
  fwd triad, swap posx/negx) — vg4 spawned 180 flipped because arm
  L/R pick was x-noise. Segfault happened 2x at game boot (transient,
  retry works).
- Scores: Likeness 6.5 / Execution 7. Judge: likeness gap now mostly
  SOURCE-inherited (blue bib swallows chest, brown mustache, round cap
  — faithfully converted). TUCK EXPLOSION GONE (675/895 "coherent
  compact mass, no explosion") — snug-cap template fixed it.
- Execution items (all general): crumpled multi-shell gloves (every
  frame), deep-pose shin/waist crumple, exposed skin back-of-head in
  tucks, atlas bleed (blue on shoe, red flecks on gloves), buttons
  drift. Next: glove shell weld/cleanup, UV gutter bleed fix, source
  template tweak (red chest dominant, black mustache, hair coverage).

## r25 (2026-08-18) — vg5, input variation round
- gpt-image-2 probing: blocks the mustachioed-mascot-with-cap-overalls
  ARCHETYPE at output stage even fully recolored (teal/tan test also
  blocked); viking control passes. Unusable for this character; fine
  for non-plumber characters. Gemini remains the path.
- vg5 = template v3 (red-dominant chest, narrow bib, wide-set buttons,
  black mustache, snug cap, hair covers back). Tripo mesh CLEAN (new
  render_tpose.py isolates provider mesh from game conversion).
- Scores: Likeness 7 / Execution 7.5 (best execution yet; ZERO
  glitches in 29 frames; tuck frames clean per judge).
- Conversion losses, all head-texture: cap M emblem didn't survive
  (source's M was low-contrast red-on-red; vg4's bold white-circle M
  DID survive), mustache smeared, skin warmed. Back-of-head hair
  ambiguous from front-only source.
- Next template (vg6): bold white-circle M, blue oval eyes (not black
  dots), narrower bib; consider Tripo multiview (front+back images)
  for rear hair coverage.

## Normal skinning fix (2026-08-18) — root cause of blocky shading
- User flagged hard shadows between faces. Root cause: OSB5 CPU-skin
  path updated vertex POSITIONS per frame but left NORMALS frozen at
  spawn pose ("st/normals static") — every face kept spawn-pose
  brightness baked on; up-bias 0.62 hack amplified crease contrast.
- Fix (general, engine): ftport.c stores per-influence joint-local
  bind normals (bind_nrm, jinv * n at load); port_osb5_skin_update
  LBS-rotates them, maps to joint-0 space, renormalizes to s8 per
  frame. port_osb5_copy_windows copies whole Vtx so it propagates.
- Converter: UP_BIAS 0.62 -> 0.0 (obsolete with rotating normals).
- In-game: smooth rounded shading matching vanilla's Gouraud look.

## r26 (2026-08-18) — vg5 + normal-skinning fix
- Likeness 6.5 / Execution 7.5. Shading complaints GONE (judge:
  correct Gouraud gradients; "motion quality alone would earn an
  8+"); geometry/deformation/effects all clean.
- Both axes now lose points almost entirely in the HEAD: no M emblem
  (bake loss), elongated droopy nose (Tripo 3D-ified the flat angular
  source nose), thin mustache, dark orange skin drift, dot eyes
  (source style). Below the neck judged near-isometric with vanilla.
- Next: vg6 source template targeting the head — bold white-circle M,
  blue oval eyes, short round bulb nose, pale peach skin, thick
  scalloped mustache. Consider Tripo multiview for rear coverage.

## r28 (2026-08-18) — vg6 (3D-render-style source + projection)
- vg6 template: "N64 model screenshot" style (3D shading cues) + big
  blue eyes + bold white-circle M + closed mouth. Tripo bake kept the
  face! In-game: eyes/emblem/skin all read correctly (cap emblem
  "arguably cleaner than vanilla's").
- New general converter passes this round:
  * --flatten: generic albedo de-shading (hue/sat-bin V median pull).
  * --project-source <img>: bind-space position+normal atlas raster,
    orthographic source re-projection onto front-facing texels with
    source-grid z-buffer (depth-select) + local-flatness detail guard
    (only paints into flat regions; never stomps baked face detail).
    Restored the M emblem. Facing cone tightened 0.35->0.55.
  * --debleed prototype (headwear hue bleed -> hair): red/brown are
    hue-neighbors; S/V discrimination works but hair sampling caught
    skin (bake has skin under sparse hair) -> repainted head bald.
    DISABLED pending better hair sampling (cluster darker V mode).
- Scores: Likeness 6.5 / Execution 7 (judge noise band ~±0.75; six
  two-axis rounds: 7.5/7, 7/6.5, 6.5/7, 7/7.5, 5.5/7, 6.5/7).
- Blockers named by judge (both axes, consistent across rounds):
  (1) tuck-pose head shred (red starburst 675/895) — correlates with
  LONG HAIR STRAND geometry (vg4 short hair = clean tuck; vg5 mild;
  vg6 strands+red = worst). Likely source-template fix: compact hair.
  (2) red-bled hair color (Tripo bake defect, not source).
  (3) slim legs vs vanilla (conform under-corrects on these sources).
  (4) buttons drift to collar (bake).

## vg7 (2026-08-18) — spot-check only, not fully scored
- vg7 source (vg6 face + red-dominant torso + compact hair) is the
  best image yet; raw Tripo mesh render is the best mesh yet (red
  chest, mid-torso buttons, thick mustache, clean emblem).
- In-game spot check: same two SYSTEMATIC Tripo defects reappear:
  (1) red cap-bleed into hair behind the ears -> neck-drape read in
  poses; happens on EVERY bake regardless of source hair length;
  (2) prominent cap brim sails in deep tuck (675) — worse here than
  vg6 because vg7's brim is longer.
- Conclusion: these two are the whole remaining gap and both are
  provider-bake systematics. Fix paths (general):
  a) --debleed with correct hair sampling (cluster lower-V mode of
     back-head texels instead of median; skin-vs-hair separation).
  b) Brim: either template "very short brim" or a general
     "headwear protrusion softening" conform on the head part.
- Champion remains vg6-skinned.osb (r28: likeness 6.5 / exec 7).
  vg7-skinned.osb built and ready for r29 once the two fixes land.

## Mao Zedong experimental run (2026-08-18) — first non-Mario character
- End-to-end with ZERO character-specific code: Gemini N64-style
  T-pose (first attempt too high-res/realistic per user; retro
  constraints prompt fixed it) -> mesh -> rig -> convert (--reskin
  --mild-color --flatten --project-source) -> inject. Facing
  auto-detect fired correctly on the Meshy rig too.
- PROVIDER NOTE: Tripo REJECTS real-person likenesses (code 2008
  content policy, both realistic and stylized). Meshy accepts.
  Meshy default mesh too dense for the port (10k verts) -> SIGBUS;
  use --polycount 4000.
- ENGINE BUG FOUND+FIXED: osb5_load had `s32 map[4096]` on the stack
  indexed by vert id -> stack smash (SIGBUS in memset) for >4096-vert
  payloads. Now malloc'd to nverts. Capacity envelope: ~5.4k verts /
  3.9k tris confirmed working in play.
- Harness note: game window opened at 3024x1770 (half res) this run —
  fixed crop coords assume 6016x3136; should read frame size and
  scale crops (TODO in run_eval or pair-builder).
- In-game: recognizable likeness, suit reads, full moveset + effects
  work (smash flash, fireball, shield). Legs squat (Mario part
  conform), ankle shading muddy. mao-skinned.osb kept.

## Mao v3 + converter hardening (2026-08-18)
- User rejected v1 quality (shredded/squished legs). Root causes found
  by payload-vs-raw-mesh isolation, in order of discovery:
  1. s_par blowup: THIS Meshy rig dropped knee joints at ankle height
     -> Mlen/mlen ~1000x -> verts flung. FIX: clamp bone-axis scale to
     0.45..1.8 x s_perp (general).
  2. Fused shoes: source image feet touching -> Meshy meshed one blob
     with interleaved L/R weights. FIXES: geometric side correction of
     part weights AND provider bone indices (lateral axis from hip
     joints, NOT hardcoded z); bridge-cut of cross-mirror tris; degen
     cut of bind-overlong tris; source template now demands clearly
     separated legs/feet.
  3. bone_map SIDE MISMATCH (big one): build_bone_map picked its own
     posx by raw x while main's facing fix could swap posx -> weights
     vs conform mirrored against each other -> total shred whenever
     facing fix landed opposite the x-noise (first hit: mao3, faces
     +/-z). FIX: bone_map now takes main's posx/negx (single source of
     truth, built after the facing fix).
  4. Facing cue: toe CENTROID defeated by blocky heels (mao3 faced
     backwards in-game). FIX: farthest-horizontal foot vert = toe;
     head-offset fallback for weak signals.
- mao3-clean.png: Gemini drew an emulator screenshot (HUD+chrome);
  cropped/painted out before meshing. Watch for this with "screenshot"
  style prompts.
- Result: mao3-skinned.osb is demo-grade (face, suit, legs, facing all
  correct; minor black tearing at boot cuffs). Delivered 4 shots.
- NOTE: the payload offline-render view labels are spawn-world, not
  bind — don't diagnose facing from them; use in-game shots.

## Mao v4 — end-to-end sweep + retarget overhaul (2026-08-18)
PROVIDERS: Tripo rejects Mao in every style (3 probes, code 2008) —
  it moderates the IMAGE likeness, not text. Meshy accepts.
  gpt-image-2 NOW generates Mao in "low-poly N64 model" phrasing (the
  earlier blocks were the mascot archetype) and gave the best source:
  clean separated limbs, visible knees, big boots (gpt-mao.png).
  Gemini "screenshot" prompts wrap fake emulator HUD -> crop it.
ROOT CAUSES of holes/wacky feet, found by torn-triangle instrumentation
(OSB_DEBUG=1 prints torn tris by part/height + pivot-agreement gaps):
  1. My degen cut by BIND edge length removed legit big low-poly tris
     -> holes. Replaced by a STRETCH-RATIO cut (world/bind > 3x).
  2. s_par clamp (from v2) broke pivot agreement -> limb tears. Removed;
     degenerate joints now fixed by CHAIN JOINT REPAIR (knee relocated
     to mid-chain + chain reweight) — Meshy drops knees at the ankle
     under trousers.
  3. Per-part PROFILE conform (vanilla Mario part bounds) tears non-
     chibi meshes at every part boundary -> --no-profile (use for
     non-Mario characters).
  4. Torso map couldn't satisfy its 5 attachments (hips 30-41u,
     shoulders 49u gaps). Full affine fit = shear -> internal torso
     tears (236). FIX: shear-free ANISOTROPIC torso map (vertical from
     length ratio, lateral from hip+shoulder width ratios, depth global)
     -> 13 torn tris. Mario's skeleton is ~1.7x wider-per-height than
     Mao's — that ratio mismatch was the whole saga.
  5. Displacement-field smoothing REVERTS intended pose rotations
     (arms back to T-pose, chin to collar). Disabled (opt-in
     --smooth-disp). Use WEIGHT smoothing (3 iters) instead.
  6. Anatomical influence clamp: leg bones can't drive verts above the
     hips; arm bones can't drive verts medial of the clavicle.
  7. Global scale = total height (vanilla head-top to ankle) not neck-
     to-ankle (Mario's head is 1/3 of his height).
RESULT: gptmao-skinned.osb — no holes, intact boots, Mario-height,
  clean stance; fsmash + utilt tuck clean in-game. Mario vg6 regression
  check with new defaults: clean.
Build: convert_rigged.py --mild-color --no-profile --flatten
  gptmao-rigged.glb mario-frames.skel gptmao-bundle.json (Meshy
  --polycount 4000 from gpt-mao.png). No --project-source (it smeared
  this face; the bake was already good).

## Joey Flynn (2026-08-21) — second real-person character, end to end
- Source: gpt-image-2 text-described N64-model T-pose, 3 iterations
  (v3 = messy gray-on-top curls, big amber glasses, dark beard, fair
  skin, chain, pocket tee, full jeans, fisherman sandals). Reference
  photos weren't on disk (chat attachments); gen.py now takes repeatable
  --ref (OpenAI images/edits multipart + Gemini multi-inline) for a
  photo-referenced likeness pass when photos are dropped in refs/.
- Providers: Tripo ACCEPTS private individuals (its block is public
  figures). But its rig came back 67k-80k verts ignoring face_limit,
  and convert_model rejected every param shape. Tripo CDN now 403s
  urllib's default UA (tripo.py sends a curl UA). Meshy --polycount
  4000 -> 7.5k verts, clean.
- New general stage: decimate_if_dense (fast_simplification quadric
  collapse, attributes remapped THROUGH THE COLLAPSE HISTORY — nearest-
  vertex remap scrambles fragmented provider atlases). Skips when the
  mesh is already near target (first version re-remapped a 7.5k mesh
  and scrambled its texture).
- Converter: joint repair fired (knees at 7-8% H), 4 torn tris.
- Result joey-skinned.osb: recognizable in play, clean stance/moves.
Build: convert_rigged.py --mild-color --no-profile --flatten
  joey3-meshy-rigged.glb mario-frames.skel joey-bundle.json

## P3 (2026-08-21) — third character, photo-referenced
- Reference photos recovered from the session transcript JSONL (user
  images are base64 in user-role messages) -> refs/p3-face.png (and
  refs/joey-*.png). gpt-image-2 images/edits with --ref gave a near-
  photo likeness on pass 2 (p3b-tpose.png).
- Both providers run: Meshy (4k) clean + forward; Tripo decimated fine
  via collapse-aware decimation (53k->2.5k) but faced BACKWARD — toe
  cue misread sneaker heels. Added --flip-facing manual override.
  Used Meshy. 3 torn tris. In-game: strong likeness, clean.
Build: convert_rigged.py --mild-color --no-profile --flatten
  p3-meshy-rigged.glb mario-frames.skel p3-meshy-bundle.json

## Sizing + "supersize" (2026-08-21)
- "Supersize head" = Mario's TAUNT camera zoom, not a scale mechanic
  (SSB64 has no mushroom; SSB64_TEST_SCALE=2.0 hook added to ftmanager
  spawn — uniform TopN scale renders correctly). What the zoom exposed
  was SIZING: Joey 397 / Mao 379 tall vs vanilla 446.
- Root cause: limbs+torso are locked to Mario's bone lengths, so height
  is set by the HEAD; Mario's head is 197u (44% of height), a human
  head at global scale ~124u. FIX (general): head part gets its own
  scale so its top lands at the vanilla head top (clamp s_perp..2.4x).
  Joey now 468 tall; in-game height parity at idle and taunt zoom.

## Tournament round 1 (2026-08-22) — 6 chars x 5 arms, 52 human A/B + LLM judge
- Human BT: E 1.43 > B 1.23 > A 0.98 = C 0.98 > D 0.38. Judge: C>A>B>E>D.
  Agreement 87% (91% non-tie), kappa 0.77. E~A visually (2-5% atlas
  px) -> E's lead is noise; D (Tripo) robustly worst for both.
- Triage tags joined with converter diagnostics:
  * torn-tri count separates corrupted Meshy cells perfectly:
    shards/corrupt >=107, clean <=102 -> GATE at ~80.
  * D failures = OUR decimation (texture remap on fragmented atlas)
    + inflated head scale (580-750) — not Tripo mesh quality. Tripo
    used to honor face_limit (2.7k-vert Mario rigs); find regression.
  * facing wrong: thomas-B only (converter flipped on sneakers) ->
    add VLM facing-verification gate.
  * C (Gemini) most shards (4/6) despite crisp faces -> drop.
  * systematic LEFT-limb artifacts (black band, flattened arm, skinny
    leg) across characters/arms -> converter bug to root-cause.
- Next: gates + re-roll, left-limb bug, Tripo face limit, rerun A/B only.

## Tournament round 2 (2026-08-22) — same images, fixed converter, Tripo v3
- Fixes in this pass: rear-forearm twist (degenerate game-side triad),
  face-detector facing gate (Haar on payload renders; caught obama-B2,
  joey-AT), torn-tri gate + re-roll, Tripo model_version v3.0-20250812
  (honors face_limit; default model ignores it).
- Human BT: BT 3.32 >> A1 0.90, AT 0.89, A2 0.45, B2 0.41, B1 0.04.
  BT beat B2 11/12, won 5/6 characters. Tripo ACCEPTS all Mario-styled
  (B) images incl. Mao/Obama -> style ref fixes the filter too.
- Controls: B1->B2 11/12 for new converter; A1->A2 human preferred
  OLD 4/6 (obama, queen not re-rolled) -> open question (head scale?
  twist?). Judge said A2 6/6 — disagrees.
- Judge agreement collapsed to 47% (kappa 0.14): geometry-weighted
  instructions made it fixate on hand shards in stills; human judged
  motion, 7 ties. Judge = gross-failure detector only until it sees
  video.
- PRODUCTION RECIPE: gpt-image-2 + Mario style ref -> Tripo v3 (4k
  faces) -> convert --no-profile --flatten + gates.
