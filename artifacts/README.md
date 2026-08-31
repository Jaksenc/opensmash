# Artifacts

`experiments/` contains historical generated character models, source images,
atlases, JSON bundles, OSB bundles, and visual reports. These files document
earlier pipeline iterations; they are not the production character roster.

The experiment files intentionally remain in one flat directory. Several JSON
bundles refer to their matching atlas by basename, and some generations reuse
an atlas from another named iteration. Keeping them together preserves those
links without rewriting historical output.

Production-ready game assets live in `play/` at the repository root.
