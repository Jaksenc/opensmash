# Character roster editorial policy

Last reviewed: 2026-09-01

This policy governs proposed real-person characters. Its purpose is taste and
product judgment, not a declaration that every included person is admirable or
that every excluded person is guilty of a crime.

The exact names currently excluded live in
`config/wikipedia-roster-exclusions.txt`. The Wikipedia seed generator applies
that file by default and replenishes the list from lower-ranked candidates so
the requested `--limit` remains exact.

## Principles

### 1. Exclude sexual abuse, child abuse, and exploitation cases

Exclude people with relevant convictions and exceptionally well-established
abuse histories. A novelty fighting-game appearance is too likely to trivialize
the conduct or become a joke at victims' expense.

An unresolved allegation is not a finding of guilt. Serious active sexual or
violent criminal proceedings belong in temporary quarantine under principle 3.

### 2. Exclude people whose prominence is inseparable from victimization

Exclude people whose appearance in the popularity source is substantially
driven by their murder, kidnapping, trafficking, sexual abuse, or similarly
personal trauma. Even when they had an independent public life, rendering them
as fighters can turn their victimization into spectacle.

This does not create a blanket ban on every person who experienced violence.
Use judgment when their lasting public identity is clearly independent of the
event, but default toward exclusion when the joke would obviously invoke the
trauma.

### 3. Quarantine serious pending criminal cases

Temporarily exclude people facing active proceedings for serious sexual or
violent crimes. This avoids both prejudging guilt and shipping a character in
the middle of a live case. Revisit after the case resolves.

Exceptions must be deliberate and recorded by name. Sean Combs is currently an
explicit exception and is not in the exclusion file.

### 4. Evil, criminality, and controversy alone are not disqualifying

Historical villains, dictators, gangsters, and recognizable true-crime figures
can be funny or legible character choices. Pablo Escobar and Charles Manson are
examples of dark inclusions that fit the intended tone.

Obscure criminals may be weak roster choices, but obscurity is a ranking and
recognizability problem rather than an automatic safety exclusion. Luigi
Mangione is specifically excluded while his real-world case remains current.

Do not exclude someone merely for being controversial, political, religious,
an adult entertainer, or broadly disliked.

### 5. Exclude hate-symbol and platforming risks

Exclude living propagandists and iconic hate-regime figures when a playful
fighter treatment is likely to look celebratory, serve as extremist signaling,
or generate screenshots that overwhelm the project's joke.

### 6. Exclude militant leadership and live-conflict symbols

Exclude people whose roster presence would primarily be read through their
leadership of an armed militant or terrorist organization, or as taking a side
in a current mass-casualty conflict. In a fighting game, the format itself can
make these inclusions feel like endorsement, recruitment imagery, or glib
commentary on ongoing deaths rather than a legible historical-villain joke.

This is not a blanket ban on soldiers, revolutionaries, heads of state,
dictators, or political figures. Apply it narrowly when militant leadership or
an unresolved conflict is the dominant modern meaning of the character. Yasser
Arafat is the line-drawing example for this rule.

### 7. Exclude sacred figures when depiction itself is a flashpoint

Exclude religious figures when turning them into a visible fighting-game
character would violate a widely observed prohibition on depiction or create a
foreseeable security risk that overwhelms the joke. Muhammad is the explicit
line-drawing example. This is not a blanket exclusion of religious leaders,
saints, theologians, or figures freely depicted in their traditions.

### 8. Exclude living minors

Do not generate current minors as real-person fighters. Reconsider them only
after they are adults and independently recognizable enough to merit inclusion.

## Repeatable review process

1. Generate a larger ranked Wikipedia/Wikidata candidate pool.
2. Manually inspect every proposed name; do not delegate the nuanced decision
   to keyword or model classification.
3. Verify unfamiliar or current cases using reliable sources. Distinguish
   convictions, pending charges, allegations, and victim status explicitly.
4. Add approved removals as exact display names to
   `config/wikipedia-roster-exclusions.txt`, grouped by principle with a short
   comment when the reason is not obvious.
5. Rerun the generator at the desired `--limit`; it must replace exclusions and
   still produce the exact requested count.
6. Periodically revisit quarantined cases, people who have reached adulthood,
   and explicit exceptions.

This is an editorial policy, not an automated moral-scoring system. When a case
does not cleanly fit a principle, record it for human review instead of silently
expanding the exclusion rule.
