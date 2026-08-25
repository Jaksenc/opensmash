# All-fighter replacement validation

## Sweep 2 (2026-08-25, post-fix regeneration)

All 12 bundles regenerated after: seam-weld ordering bugfix (welds now
actually reach bundles), torn-edge weld, crush-class weld guards, BLNK
blank list from mapped joints, Yoshi crash/head fixes, Yoshi tail blanked.
Booted in the wasm harness, screenshot per fighter (gallery artifact
"Twelve Thrones"). 12/12 boot and play, 0 crashes.

| fkind | fighter | mesh | notes |
|---|---|---|---|
| 0 | Mario   | GOOD | baseline |
| 1 | Fox     | GOOD | tail preserved (accessory), clean |
| 2 | Donkey  | GOOD | tie preserved; knuckle-walk correct; hem holds |
| 3 | Samus   | GOOD | asymmetric arms handled |
| 4 | Luigi   | GOOD | identity map |
| 5 | Link    | GOOD | sword + shield preserved with game logic |
| 6 | Yoshi   | GOOD | all fixes verified; tail deliberately blanked |
| 7 | Captain | GOOD | clean |
| 8 | Kirby   | POOR | crush-class: flower-height shards (weld guards keep it from vanishing entirely; welding a global crush collapses the mesh to a point) |
| 9 | Pikachu | POOR | tiny but readable; vanilla ears/tail poke through |
| 10 | Purin  | POOR | crush-class, crumpled flower-height figure |
| 11 | Ness   | GOOD | clean |

## Link green-vertex leak — root cause (2026-08-25, user-reported)

Playing queen-as-Link showed green tunic fragments. Three layered causes,
each general:

1. **Unmapped-geometry joints are not all accessories.** The blank list
   keeps every joint the profile doesn't map, on the assumption those are
   accessories. For Link that wrongly kept joint 24 (his CAP — the long
   green tail hanging behind the head, the visible fragment) and joint 5
   (a torso piece). Position audit across all skeletons found the same
   class on most fighters: chest/torso joint 5 nearly everywhere,
   Captain's shoulder piece 18, Ness's backpack 23/28/29. All profiles now
   carry explicit `blank_extra` (true accessories confirmed kept: DK tie,
   Fox tail, Pikachu ears+tail, Link sword+shield).
2. **Stale bundle staging.** `package_web.sh` wiped `web-dist/bundles/`,
   and ad-hoc restaging re-copied OLD `/tmp/queen-*.osb` (pre-BLNK
   overnight builds) over the regenerated ones for 7 of 11 fighters — so
   the neck-piece fix (joint 22, in the map-values blank list) never
   reached play. `package_web.sh` now preserves `bundles/` across
   repackages, `pipeline/play/` is the canonical bundle store, and the
   stale /tmp copies are deleted.
3. The original chain-joint leak (Yoshi's head class) had already been
   fixed by the BLNK list; Link's joint 22 (neck piece) was the subtle
   instance of it.

## Sweep 1 (overnight 2026-08-25, pre-fix — for history)

Queen Elizabeth II converted onto every fighter skeleton and booted in the
wasm harness (`?inject=bundles/queen-<name>.osb&fkind=<k>&SSB64_BOOT_BATTLE=<k>,8,4`).

| fkind | fighter | mesh | notes |
|---|---|---|---|
| 0 | Mario   | GOOD | baseline (weirdal/joey/queen all verified previously) |
| 1 | Fox     | GOOD | tail preserved (accessory joint), clean stance/moves |
| 2 | Donkey  | GOOD | tie preserved; knuckle-walk correct; seam-weld closes the hem |
| 3 | Samus   | GOOD | asymmetric arms handled; her hand replaces the cannon visual; shots fine |
| 4 | Luigi   | GOOD | identity map |
| 5 | Link    | GOOD | sword + shield preserved with their game logic |
| 6 | Yoshi   | GOOD | crash fixed (typed blanking + interpreter guard) + vanilla-head leak fixed (BLNK list); tail later blanked by choice |
| 7 | Captain | GOOD | clean run cycle |
| 8 | Kirby   | RUNS | severe crush: whole humanoid onto ball body — visually poor, playable |
| 9 | Pikachu | RUNS | very small result; ears/tail preserved; proportions readable but tiny |
| 10 | Purin  | RUNS | same crush class as Kirby |
| 11 | Ness   | GOOD | clean |

## Yoshi crash (FIXED 2026-08-25)

Root cause was two-layered, both general (not Yoshi-specific — Yoshi is just
the first fighter whose parts exercise these paths):

1. **Union-typed parts.** `FTParts.flags & 0xF == 1` parts treat the DObj
   display-list union as a `Gfx **` token-pair array (`dobj->dls`), not a
   plain `Gfx *`. Our blanking wrote `sOsb5NullDL` (a real Gfx) into what the
   drawer then dereferenced as a pointer table, yielding raw GBI words
   (0xE7.../0xDF...) as "DL pointers". Fix in `ftport.c`: type-aware
   blanking — `osb5_blank_joint()` writes a `{NULL,NULL}` pair
   (`sOsb5NullDLPair`) for flags-1 parts and `sOsb5NullDL` otherwise;
   `osb5_joint_is_blanked()` checks the matching field; the self-heal loop
   and the modelpart guard both use these. The root joint's parts flags are
   forced to plain (`flags &= ~0xF`) since we install a real mesh DL there.

2. **Game-built runtime DLs embed joint dl words.** Some Yoshi path (the
   egg/hidden-part graft around frame 44) copies `joint->dl` first-words into
   a runtime display list, so even a correctly-typed blank DL leaks a
   widened-host-Gfx word (0xDF00000000000000) as a G_DL *target*. Fix in
   `libultraship/src/fast/interpreter.cpp` (`gfx_dl_handler_common`): skip
   command-shaped DL targets (32-bit addr with top byte >= 0xD0, or a 64-bit
   value outside canonical pointer range) with a warning instead of
   executing them. This also hardens every other fighter against the same
   class of stray pointer.

Verified: native 1440+ frames clean, wasm 3700+ frames clean, visual check
in browser shows the replacement mesh animating with Yoshi's shell/tail
accessories preserved. Mario-path regression run clean (guard never fires).

## Yoshi vanilla-head leak (FIXED 2026-08-25)

After the crash fix, Yoshi's vanilla green head still drew over the
replacement. Cause: blanking was driven by the bundle's *skinned* joint set
(the 14 canonical weighted parts, remapped), but non-Mario skeletons carry
body geometry on chain joints no canonical part maps to — Yoshi's joint 7
(neck) holds most of his head, joint 5 his hips.

General fix, three pieces:
- The converter now emits an explicit **BLNK** section in OSB5: every target
  joint the profile *maps* a canonical body joint onto (the map itself
  declares them body joints) plus per-profile `blank_extra` (yoshi: `[5]`).
  Unmapped joints are accessories (sword/shield/tie/tail/ears) and keep
  vanilla DLs + modelparts 1:1.
- The engine blanks/self-heals/modelpart-guards from the BLNK list when
  present, falling back to the skinned joint set for old bundles (verified:
  old-format queen-link bundle runs unchanged).
- Audit of every skeleton (dv joints minus mapped minus blank_extra) shows
  the remaining unmapped-geometry joints are exactly the accessories:
  captain/donkey [5,18], fox [5,28,29], link [5,11,19,24],
  ness [23,28,29], pikachu [5,13,14,29], samus [5], yoshi [19,20].
  Joint 5 (a hip piece) stays vanilla on validated-GOOD fighters; it sits
  inside the replacement mesh there. Add it to `blank_extra` per profile if
  it ever peeks through.

## Accessory snap (ACCS section, 2026-08-25)

Kept-vanilla accessories attach at their vanilla bind offset from the
parent joint, which sits flush against the VANILLA body — Yoshi's tail
root floated 71 world units behind the thinner replacement mesh, and a
static parent-local delta still drifted because the vanilla parent (hips 5)
and the mesh's own skinned joints animate apart (crouches, runs).

General mechanism: profile `snap_accessories` lists accessory ROOT joints
(children ride along). The converter finds the nearest replacement-mesh
vertex to the root's bind position, embeds 28 units inside the surface
(accessory geometry hangs off the whole chain, so a root ON the surface
still leaves the visible base shy of the body), takes the dominant-weight
joint of that vertex as the ANCHOR, and emits {joint, anchor,
offset-in-anchor-bind-frame} as an OSB5 **ACCS** section. Every tick
(post-anim, pre-draw) the engine recomputes the root's parent-local
translate so its world position tracks the anchored surface point through
any pose — verified flush in idle/run/crouch and across a KO + respawn.
Yoshi: `[19]` (anchor resolves to torso 6). Opt-in per profile; absent
section = vanilla placement, so validated fighters are untouched until a
profile declares a snap.

## Original crash notes (for history)

SIGSEGV, deterministic at ~frame 44 (his first status change after spawn —
the entry/egg transition, right after `ftMainUpdateHiddenPartID fkind=6
hpid=1 joint=1 parent=0 kind=3` grafts a new DObj over joint 0's children
and installs it as fp->joints[1]). Renderer later walks a DL head of
0xE7000000 (a raw G_RDPPIPESYNC word read as a pointer).

Bisection (env gates left in ftport.c/ftparam.c: SSB64_NO_SELFHEAL,
SSB64_NO_MPGUARD, SSB64_NO_BLANK, SSB64_NO_ROOTDL, SSB64_NO_SKIN,
SSB64_SKIN_FRAMES_ONLY, SSB64_SKIN_UPTO, SSB64_NO_ROOTFRAME):
- vanilla Yoshi: clean (native + wasm)
- injection with ALL writes disabled (no root DL, no blanking, no skin
  internals): clean 840+ frames
- ANY single write path enabled crashes at the same frame:
  (a) root mesh DL on joints[0], (b) blanking bundle joints' dls,
  (c) the skinning frame walker (gmCollisionGetFighterPartsWorldPosition
  cache writes) — even only for joint 0.
- bundle validated offline: joint refs, weights, positions all sane.

Working theory: the hidden-part graft (egg) interacts with any foreign
dl/parts state — possibly the FTParts bump allocator or a dl_link/dist_dl
walker that assumes vanilla dl values on his joints. Next step: dump
Yoshi's hiddenparts table + instrument gcDrawDObjTreeDLLinks bail logs
during the frame-44 transition.

## Stub fighters (Kirby/Purin/Pikachu) — quality gap

The canonical humanoid chain maps onto 1-2 segment stubs; parts crush by
design but the result reads as a blob. Ideas: per-part uniform mini-scale
(shrink the whole character into the ball footprint instead of per-bone
crushing), or dedicated chibi source meshes for stub fighters.
