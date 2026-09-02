# Overnight S+A batch — 2026-09-02

- List: config/seed-roster/seed-roster-sa.txt (1053 names, S+A tiers; "Queen Elizabeth the Second" dropped: slug collision with "the First" and duplicates existing `queen`)
- Built: 1034 characters (after morning steered re-runs) (play/<slug>.osb6 + play/ui/<slug>/). Not yet published to web-prototype/config/characters.json.
- Blocked: 19, all image-moderation (Manson skipped by user). Ledger: batch-state/moderation-blocked.txt (name, stage, input/output, provider category).
- Spend: ~$650 (cost.json sum). Tripo balance after: 28,060 credits. Wall: 3.5 h at 16 workers.

## Blocked, by fix
- Real people refused at the t-pose (input, "public-figure"): Gandhi, Kim Kardashian, Michael Jackson, Mister Rogers, Charles Manson, LeBron James, Walt Disney, Ellen DeGeneres, Michael Schumacher, Saddam Hussein, Bryan Cranston. Name must be in that prompt for likeness; no pipeline fix, provider policy.
- Xi Jinping: OpenAI drew him, Tripo refused the image (content policy).
- Copyrighted design drawn at the t-pose (output): Oswald, Pinocchio, Winnie the Pooh, Cheshire Cat, Captain Hook, Peter Pan (Disney); Loki, Thor, Chris Hemsworth (Marvel); Christopher Reeve (Superman), Lynda Carter (Wonder Woman), Daniel Radcliffe (Potter), Carrie Fisher (Leia); Homer (drawn as Simpson); Paul Bunyan. Re-run with `--notes "..."` steering the depiction (e.g. Homer: "the ancient Greek epic poet"; Loki/Thor: "Norse mythology, not Marvel"; actors: "in a plain suit, not the film costume").
- Michelangelo's David: nudity (output). `--notes "wearing a simple tunic"`.
- Emblem only (everything else built): Adam West, Ryan Reynolds. `run_character.py "<name>" --emblem "<non-trademark object>"`.
- Portrait only: The Tooth Fairy (output block twice). Try `--force-stage portrait` once more or a note.

## Code changed during the run (uncommitted, pipeline repo)
pipeline/run_character.py (portrait prompt no name, emblem name-free fallback, Tripo cost fallback, keep non-terminal Tripo tasks, wider task timeouts, empty-response error),
pipeline/tripo.py (429 wait on Retry-After), pipeline/convert_rigged.py (joint_ids union, writer safety net, atomic writes),
pipeline/expand_character.py (pixel-budget short-name wording), scripts/batch_characters.py (driver), config/seed-roster/seed-roster-sa.txt.

## Morning pass (08:45-08:55)
- Gandhi: display name shortened to "Gandhi" (full name refused at the t-pose input filter); stock icon drawn from the description (new general fallback in run_character when the likeness is refused at that stage). Built.
- Steered re-runs with --notes (new run_character flag): Cheshire Cat, Loki, Thor, Hemsworth, Reeve, Lynda Carter, Radcliffe, Carrie Fisher, Homer (Greek poet), Paul Bunyan, David (tunic) — all built.
- Still blocked (output filter judges the image itself; PD-design notes did not help): Oswald, Pinocchio, Winnie the Pooh, Captain Hook, Peter Pan.
- Charles Manson: skipped by user.
