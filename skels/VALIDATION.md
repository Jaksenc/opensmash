# All-fighter replacement validation (overnight run, 2026-08-25)

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
| 6 | Yoshi   | CRASH | see below |
| 7 | Captain | GOOD | clean run cycle |
| 8 | Kirby   | RUNS | severe crush: whole humanoid onto ball body — visually poor, playable |
| 9 | Pikachu | RUNS | very small result; ears/tail preserved; proportions readable but tiny |
| 10 | Purin  | RUNS | same crush class as Kirby |
| 11 | Ness   | GOOD | clean |

## Yoshi crash (open)

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
