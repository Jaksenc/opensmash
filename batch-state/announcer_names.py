#!/usr/bin/env python3
"""Propose announcer-length display names for the existing roster (text-only,
~$0.0003 each) -> batch-state/announcer-names.csv (slug, current display,
proposed, reason). Review, then apply with --apply (rewrites character.json
display, keeps name_full, deletes announcer.wav so run_character regenerates
the clip) — --apply only touches rows whose proposed != current."""
import csv, json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "pipeline"); from gen import http, ENV, token_cost
RULE = ('You name fighters for a 1999 arena fighting game. Given the roster entry and its description, return the name the '
        'ARENA ANNOUNCER shouts when the fighter is picked, which is also shown as the in-game name: the shortest form a crowd '
        'would instantly recognise, natural casing, spaces allowed. Surname alone when world-famous by it (Wolfgang Amadeus '
        'Mozart -> Mozart; Albert Einstein -> Einstein; Winston Churchill -> Churchill). First or stage name alone when that is '
        'the famous form (Cher; Beyoncé; Hercules; Madonna). Full name when both halves are needed (Marilyn Monroe; Michael '
        'Jackson; Bill Gates; George Washington). Keep an iconic title (Pope Francis; Queen Elizabeth; Captain Hook; Mister '
        'Rogers). Strip descriptive qualifiers/epithets ("Hercules the Greek Hero" -> Hercules; "Thor the Norse God" -> Thor; '
        '"Michelangelo\'s David" -> David; "The Statue of Liberty" stays as is because that is the name). Never an abbreviation. '
        'If the current display is already right, return it unchanged.')
SCHEMA = {"type": "object", "properties": {"display": {"type": "string"}, "reason": {"type": "string"}},
          "required": ["display", "reason"], "additionalProperties": False}
def propose(entry, display, desc, model="gpt-5.6-luna"):
    r = http("https://api.openai.com/v1/responses", "POST", {"Authorization": f"Bearer {ENV['OPENAI_API_KEY']}"},
             {"model": model, "instructions": RULE,
              "input": [{"role": "user", "content": [{"type": "input_text", "text": f"Roster entry: {entry}\nCurrent display: {display}\nDescription: {desc[:300]}"}]}],
              "reasoning": {"effort": "none"},
              "text": {"format": {"type": "json_schema", "name": "announcer", "strict": True, "schema": SCHEMA}},
              "max_output_tokens": 200, "store": False})
    text = r.get("output_text") or "".join(p.get("text", "") for it in r.get("output", []) if it.get("type") == "message"
                                          for p in it.get("content", []) if p.get("type") == "output_text")
    return json.loads(text)
slug = lambda n: re.sub(r"[^a-z0-9]", "", n.lower())[:16]
names = {}
for l in open("config/seed-roster/seed-roster-sa.txt"):
    if l.strip() and not l.startswith("#"):
        n = l.split("\t")[0].strip(); names[slug(n)] = n
if "--apply" in sys.argv:
    n = 0
    for row in csv.DictReader(open("batch-state/announcer-names.csv")):
        if row["proposed"].strip() and row["proposed"] != row["current"]:
            p = f"play/ui/{row['slug']}/character.json"; d = json.load(open(p))
            d.setdefault("name_full", row["entry"]); d["display"] = row["proposed"]
            json.dump(d, open(p, "w"), indent=1)
            w = f"play/ui/{row['slug']}/announcer.wav"
            if os.path.exists(w): os.rename(w, w + ".old")
            n += 1
    print(f"applied {n} renames; run the voice stage to regenerate their clips"); sys.exit()
slugs = sorted(s for s in os.listdir("play/ui") if os.path.exists(f"play/ui/{s}/character.json"))
def one(s):
    d = json.load(open(f"play/ui/{s}/character.json")); entry = names.get(s, d.get("name_full", d.get("display", s)))
    try: v = propose(entry, d.get("display", ""), d.get("desc", ""))
    except Exception as e: v = {"display": "", "reason": "error " + str(e)[-80:]}
    return {"slug": s, "entry": entry, "current": d.get("display", ""), "proposed": v["display"], "reason": v["reason"]}
with ThreadPoolExecutor(8) as ex: rows = list(ex.map(one, slugs))
with open("batch-state/announcer-names.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["slug", "entry", "current", "proposed", "reason"]); w.writeheader(); w.writerows(rows)
ch = [r for r in rows if r["proposed"] and r["proposed"] != r["current"]]
print(f"{len(rows)} characters, {len(ch)} proposed renames -> batch-state/announcer-names.csv")
for r in ch[:40]: print(f"  {r['current']!r:40} -> {r['proposed']!r}")
