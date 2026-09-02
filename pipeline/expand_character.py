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
                      [--emblem "context or an explicit object"]
Prints JSON: {"display": ..., "short": ..., "desc": ..., "emblem": ..., "refs": [...]}
"""
import argparse
import base64
import json
import re

try:
    from .gen import http, ENV, token_cost
except ImportError:  # direct execution: python3 pipeline/expand_character.py
    from gen import http, ENV, token_cost

# The roster tile caption is drawn in the vanilla 48px tile's pixel font
# (pixel_font.py): 42 face pixels wide at zero tracking. Anything wider gets
# condensed or truncated, so the prompt states the budget in pixels rather
# than a character count (EISENHOWER -> IKE instead of EISENHOW).
CAPTION_BUDGET_PX = 42
CAPTION_WIDTH_RULE = ("Letter widths in pixels: I=1; E F J L S Z=4; N=6; M W=7; every other "
                      "letter=5; letters butt together with no gap. The whole label must be "
                      f"at most {CAPTION_BUDGET_PX} pixels wide (about 8 average letters).")


FORBIDDEN = ["handbag", "purse", "bag", "cane", "walking stick", "sword", "umbrella", "staff",
             "scepter", "sceptre", "rifle", "gun", "pistol", "phone", "cup", "mug", "briefcase",
             "suitcase", "backpack", "shield", "spear", "guitar", "book", "baton", "leash",
             "cigar", "cigarette", "pipe", "microphone", "trophy", "flag", "torch", "lantern", "wand",
             "broom", "axe", "hammer", "bat", "racket", "ball", "clipboard", "tablet", "laptop"]

SYSTEM = """You write one-line visual descriptions of characters for a low-poly fighting-game character pipeline.
Output ONLY a JSON object {"display": <name>, "short": <short name>, "desc": <description>, "emblem": <emblem object>}.
"short" is the in-game roster label: UPPERCASE A-Z only, no spaces or punctuation, and it must FIT THE TILE: """ + CAPTION_WIDTH_RULE + """ Choose the conventional name by which people identify the character, not the longest string that happens to fit. Prefer a defining title (Queen Elizabeth II -> QUEEN), a familiar surname (Barack Obama -> OBAMA; Abraham Lincoln -> LINCOLN; Michael Jackson -> JACKSON), or an established multi-word stage name with spaces removed (Weird Al Yankovic -> WEIRDAL). Keep a canonical one-word character name intact (JIGGLYPUFF). For an ordinary multi-word personal name, prefer a complete distinctive surname when it works (Mark Kupa -> KUPA), or the complete joined name only when that is clearer. Never invent a cryptic hybrid such as MKUPA or cut a word off arbitrarily such as MARKKU. Shorter is better when it is equally recognizable.
The description is a single sentence (60-110 words) starting with the character's name, covering: face (shape, skin tone, notable features), hair/facial hair, eyes, and ONE iconic outfit described as flat solid colors from head to toe including shoes.
HARD RULES:
- Worn or attached items are allowed (hats, glasses, watches, jewelry, belts, badges, headphones, capes that are part of the outfit).
- The character must hold NOTHING and nothing may hang from the arms or hands: no handbags, purses, bags, canes, walking sticks, swords, umbrellas, staffs, weapons, phones, cups, books, instruments. Hands are empty and bare or gloved.
- No free-hanging cloth: no capes, cloaks, trailing scarves, long open coats, flowing gowns or flared/pleated skirts — thin loose sheets tear when the mesh is animated. Describe fitted equivalents instead (a fitted knee-length dress, a cropped or buttoned jacket, a tunic over trousers). Any skirt or dress is worn over opaque tights or leggings so no bare skin is under it.
- No pure-black outfits and no mirror or metallic surfaces: use charcoal grey with visible seams, matte finishes.
- No text, logos or fine patterns; no fabric texture; mouth closed; age and build stated.
- If the name is ambiguous or fictional, describe the most widely recognized depiction.
- If the name is a duo, band, group or team, describe exactly ONE member (the most iconic one) as a single figure; never two figures.
"emblem" names ONE concrete object for the character's series emblem — a short noun phrase ("a jewelled crown", "a red accordion"), the object that instantly signals this character: something they are famous for, wear, use, or are inseparable from. Never the character, their face or their body. It is drawn as a bold one-colour stencil, so prefer an object with a distinctive outline AND large internal structure (crown, accordion, pocket watch, open book, lighthouse) over a plain disc, ball, shield, generic badge or logo roundel. If the subject is not a public figure, infer the object from what the photo and notes show — clothing, gear, setting, a distinctive accessory or hobby.
"""

CHARACTER_SCHEMA = {
    "type": "object",
    "properties": {
        "display": {"type": "string"},
        "short": {"type": "string"},
        "desc": {"type": "string"},
        "emblem": {"type": "string"},
    },
    "required": ["display", "short", "desc", "emblem"],
    "additionalProperties": False,
}


def response_text(response):
    """Extract assistant text from a raw Responses API response."""
    if response.get("output_text"):
        return response["output_text"]
    return "".join(
        part.get("text", "")
        for item in response.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    )


def expand(name, photo=None, notes=None, model="gpt-5.6-luna", emblem=None):
    prompt = (f"Character: {name}"
              + (f"\nNotes: {notes}" if notes else "")
              + (f"\nEmblem context (use this for \"emblem\"): {emblem}" if emblem else ""))
    content = [{"type": "input_text", "text": prompt}]
    if photo:
        mime = "image/jpeg" if photo.lower().endswith((".jpg", ".jpeg")) else "image/png"
        data = base64.b64encode(open(photo, "rb").read()).decode()
        content += [
            {"type": "input_image", "image_url": f"data:{mime};base64,{data}"},
            {"type": "input_text", "text": "Describe the person in the attached photo so the likeness is preserved (hair, beard, glasses, skin tone, face shape, expression, clothing)."},
        ]
    out = http("https://api.openai.com/v1/responses", "POST",
               {"Authorization": f"Bearer {ENV['OPENAI_API_KEY']}"},
               {"model": model,
                "instructions": SYSTEM,
                "input": [{"role": "user", "content": content}],
                "reasoning": {"effort": "none"},
                "text": {"format": {"type": "json_schema",
                                      "name": "character_description",
                                      "strict": True,
                                      "schema": CHARACTER_SCHEMA}},
                "max_output_tokens": 1000,
                "store": False})
    text = response_text(out)
    cost = token_cost(model, out.get("usage"))
    m = re.search(r"\{.*\}", text, re.S)
    obj = json.loads(m.group(0)) if m else {"display": name, "desc": text.strip()}
    obj.setdefault("display", name)
    obj["refs"] = [photo] if photo else []
    obj.setdefault("emblem", "")
    obj["cost_usd"] = cost
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
    ap.add_argument("--model", default="gpt-5.6-luna")
    ap.add_argument("--emblem", default=None,
                    help="context for the series emblem, or the object itself "
                         "(default: inferred from the name/photo)")
    a = ap.parse_args()
    obj = expand(a.name, a.photo, a.notes, a.model, a.emblem)
    if "warning" in obj:
        # one retry with the violation called out
        obj2 = expand(a.name, a.photo,
                      (a.notes or "") + " REMOVE any held/hanging item; " + obj["warning"],
                      a.model, a.emblem)
        spent = (obj.get("cost_usd") or 0) + (obj2.get("cost_usd") or 0)
        if "warning" not in obj2:
            obj = obj2
        obj["cost_usd"] = spent
    print(json.dumps(obj, indent=1))


if __name__ == "__main__":
    main()
