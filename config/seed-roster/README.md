# Seed roster for the big run

- `seed-roster.csv` — master file. One row per fighter: rank (run order), tier (S gold / A strong / B ordinary / C noise, hand-judged on silhouette distinctiveness and comedy value), name (announcer form), section, 3-month Wikipedia pageviews (fame proxy), resolved Wikipedia title, flag (audit note). Everything else is derivable from this.
- `seed-roster-ranked.txt` — names only, in run order: tier S first, then A, B, C; within each tier a category round-robin (fictional sub-headers count as their own categories), pageviews as the tiebreak. Tier S is ranks 1-277, S+A ends at 1054.
- `seed-roster.txt` — the sectioned source list used to build the CSV.
- `seed-roster-audit.md` — every removal, rename, flag, and the reasoning.
- `seed-roster-wikicheck.tsv` — raw Wikipedia coverage check.
- `sources/` — the two 1000-name lists this was massaged from.
