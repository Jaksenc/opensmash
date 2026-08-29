#!/usr/bin/env python3
"""Second-opinion visual judge via the codex CLI (cross-model robustness:
Claude iterates, codex grades the same strip blind).

  judge.py strip.png "are the arms coherent tubes (not squiggles)?"

Prints codex's verdict: YES/NO, GRADE 1-10, ISSUES list. Exits 0 always
(the caller reads text, it doesn't gate).
"""
import subprocess
import sys
import tempfile
import os

PROMPT = """You are judging a rendered N64-style chibi fighter (a real person's
likeness on a Super Smash Bros 64 skeleton). Attached is a contact strip of
in-game poses. Judge ONLY: {question}

Answer in EXACTLY this format:
VERDICT: YES or NO
GRADE: <1-10, 10 = flawless>
ISSUES: <comma-separated list of the worst concrete visual problems you see,
with which pose panel each appears in; say "none" if clean>
SUGGESTION: <one sentence, the single most impactful fix>"""


def judge(image, question, model="gpt-5.6-sol"):
    out = tempfile.mktemp(suffix=".txt")
    r = subprocess.run(
        ["codex", "exec", "-i", image, "-m", model,
         "-c", 'model_reasoning_effort="high"',
         "--sandbox", "read-only", "-o", out,
         PROMPT.format(question=question)],
        capture_output=True, text=True, timeout=300)
    if os.path.exists(out):
        txt = open(out).read().strip()
        os.unlink(out)
        return txt
    return f"(codex failed: {r.stderr[-300:]})"


if __name__ == "__main__":
    print(judge(sys.argv[1], sys.argv[2]))
