#!/usr/bin/env python3
"""Character expander: name (+ optional reference photo) -> canonical
description used by the T-pose prompt wrapper.

The expander owns the CONTENT rules; the wrapper (eval/build_matrix.py
N64_TEMPLATE) owns the STYLE rules. Content rules:
  * worn/attached items are fine (hats, glasses, watches, jewelry, belts,
    badges, headphones) — they mesh as part of the body.
  * NO held or hanging items (handbags, canes, swords, umbrellas, phones,
    cups, weapons, staffs, bags, leashes) — thin blended geometry that
    shreds under the retarget. Hands must be empty.
  * one outfit, solid colors, closed mouth, neutral stance-friendly pose.

Usage:
  expand_character.py "Queen Elizabeth II" [--photo refs/x.png] [--notes "..."]
Prints JSON: {"display": ..., "desc": ..., "refs": [...]}
"""
import argparse
import base64
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gen import http, ENV  # noqa: E402

FORBIDDEN = ["handbag", "purse", "bag", "cane", "walking stick", "sword", "umbrella", "staff",
             "scepter", "sceptre", "rifle", "gun", "pistol", "phone", "cup", "mug", "briefcase",
             "suitcase", "backpack", "shield", "spear", "guitar", "book", "baton", "leash",
             "cigar", "cigarette", "pipe", "microphone", "trophy", "flag", "torch", "lantern", "wand",
             "broom", "axe", "hammer", "bat", "racket", "ball", "clipboard", "tablet", "laptop"]

SYSTEM = """You write one-line visual descriptions of characters for a low-poly fighting-game character pipeline.
Output ONLY a JSON object {"display": <name>, "desc": <description>}.
The description is a single sentence (60-110 words) starting with the character's name, covering: face (shape, skin tone, notable features), hair/facial hair, eyes, and ONE iconic outfit described as flat solid colors from head to toe including shoes.
HARD RULES:
- Worn or attached items are allowed (hats, glasses, watches, jewelry, belts, badges, headphones, capes that are part of the outfit).
- The character must hold NOTHING and nothing may hang from the arms or hands: no handbags, purses, bags, canes, walking sticks, swords, umbrellas, staffs, weapons, phones, cups, books, instruments. Hands are empty and bare or gloved.
- No text, logos or fine patterns; no fabric texture; mouth closed; age and build stated.
- If the name is ambiguous or fictional, describe the most widely recognized depiction.
"""


def expand(name, photo=None, notes=None, model="gemini-flash-latest"):
    parts = [{"text": SYSTEM + f"\nCharacter: {name}" + (f"\nNotes: {notes}" if notes else "")}]
    if photo:
        mime = "image/jpeg" if photo.lower().endswith((".jpg", ".jpeg")) else "image/png"
        parts.append({"inlineData": {"mimeType": mime, "data": base64.b64encode(open(photo, "rb").read()).decode()}})
        parts.append({"text": "Describe the person in the attached photo so the likeness is preserved (hair, beard, glasses, skin tone, face shape, expression, clothing)."})
    out = http(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
               "POST", {"x-goog-api-key": ENV["GEMINI_API_KEY"]},
               {"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.4}})
    text = out["candidates"][0]["content"]["parts"][0]["text"]
    m = re.search(r"\{.*\}", text, re.S)
    obj = json.loads(m.group(0)) if m else {"display": name, "desc": text.strip()}
    obj.setdefault("display", name)
    obj["refs"] = [photo] if photo else []
    # mechanical backstop for held items
    low = obj["desc"].lower()
    hits = [w for w in FORBIDDEN if re.search(r"\b" + re.escape(w) + r"s?\b", low)]
    if hits:
        obj["warning"] = f"forbidden held-item terms present: {hits}"
    return obj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--photo", default=None)
    ap.add_argument("--notes", default=None)
    ap.add_argument("--model", default="gemini-flash-latest")
    a = ap.parse_args()
    obj = expand(a.name, a.photo, a.notes, a.model)
    if "warning" in obj:
        # one retry with the violation called out
        obj2 = expand(a.name, a.photo, (a.notes or "") + " REMOVE any held/hanging item; " + obj["warning"], a.model)
        if "warning" not in obj2:
            obj = obj2
    print(json.dumps(obj, indent=1))


if __name__ == "__main__":
    main()
