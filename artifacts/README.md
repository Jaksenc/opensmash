# Artifacts

`experiments/` contains historical generated character models, source images,
atlases, JSON bundles, OSB bundles, and visual reports. These files document
earlier pipeline iterations; they are not the production character roster.

The experiment files intentionally remain in one flat directory. Several JSON
bundles refer to their matching atlas by basename, and some generations reuse
an atlas from another named iteration. Keeping them together preserves those
links without rewriting historical output.

`batch-1000/` is the record of the 1000-fighter batch run: the driver's final
`results.jsonl` / `failures.jsonl`, the facing, mesh and depiction sweeps and
the one-off scripts that produced and acted on them, the announcer-name
review CSVs, and `SUMMARY.md`. The scripts hardcode paths relative to the
repository root. `batch-state/` (gitignored) is the driver's live working
state.

`seed-roster/` is how the batch's roster was assembled: the master CSV with
tiers and ordering, the audit of every removal and rename, and the two
1000-name source lists. The generator's live inputs are
`config/wikipedia-roster-{inclusions,exclusions}.txt`.

Generated fighters live in `play/` (gitignored, published to GCS).
