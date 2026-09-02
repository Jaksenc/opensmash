#!/usr/bin/env python3
"""Re-run the copyrighted-design t-pose blocks with --notes steering the depiction.
Each name: --force-stage expand (so the notes reach the description), then the
pipeline resumes at the missing t-pose. One extra attempt on an output-side block."""
import subprocess, sys, json, time
from concurrent.futures import ThreadPoolExecutor
NOTES = {
 "Oswald the Lucky Rabbit": "the 1927 public-domain black-and-white rubber-hose cartoon rabbit: long black ears, white face, black body, shorts; original 1920s newspaper-cartoon styling, not the modern Disney redesign",
 "Pinocchio": "the wooden marionette boy from Carlo Collodi's original 1883 Italian book illustrations (Enrico Mazzanti / Attilio Mussino): pointed paper hat, long thin nose, wooden limbs; NOT the Disney film design",
 "Winnie the Pooh": "the 1926 E. H. Shepard book-illustration bear: plain golden-tan teddy bear with a round belly, no red shirt, no clothing; NOT the Disney design",
 "The Cheshire Cat": "the 1865 John Tenniel book-illustration cat: a broad-faced striped tabby with a huge toothy grin; NOT the purple-pink Disney version",
 "Captain Hook": "an Edwardian pirate captain as in J. M. Barrie's 1911 book illustrations: long black curls, red frock coat, lace cuffs, iron hook for a hand; NOT the Disney film design",
 "Peter Pan": "the boy from J. M. Barrie's 1911 book illustrations (F. D. Bedford style): tunic of leaves and cobwebs, bare feet, tousled hair; NOT the green-tights Disney design",
 "Loki the Norse God": "the Norse mythology trickster god as a Viking-age figure: braided dark hair, fur-trimmed green wool tunic, leather belt, no horned helmet; NOT the Marvel character",
 "Thor the Norse God": "the Norse mythology thunder god as a Viking-age warrior: red beard, iron-studded leather and fur tunic, belt; NOT the Marvel character, no cape",
 "Chris Hemsworth": "the actor as himself off-screen: short blond hair, stubble, plain grey t-shirt and jeans; NOT any film costume",
 "Christopher Reeve": "the actor as himself in the 1980s: dark hair, blue suit and tie; NOT the Superman costume",
 "Lynda Carter": "the actress as herself in the late 1970s: long dark hair, casual blouse and jeans; NOT the Wonder Woman costume",
 "Daniel Radcliffe": "the actor as an adult as himself: short dark hair, stubble, dark jacket over a t-shirt; NOT Harry Potter, no glasses, no robes",
 "Carrie Fisher": "the actress as herself in the 1980s: shoulder-length brown hair, casual sweater and trousers; NOT the Princess Leia costume or hair buns",
 "Homer": "the ancient Greek epic poet: elderly blind bard with a long white beard, white chiton and himation, headband; NOT Homer Simpson",
 "Paul Bunyan": "the giant lumberjack folk hero: thick black beard, red-and-black plaid flannel shirt, blue jeans, suspenders, boots; empty hands, no axe",
 "Michelangelo's David": "the marble statue depicted wearing a simple knee-length white tunic; skin and hair in matte white marble; no nudity",
}
def run(name, notes):
    for attempt in (1, 2):
        cmd = [sys.executable, "pipeline/run_character.py", name, "--notes", notes] + (["--force-stage", "expand"] if attempt == 1 else [])
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=2400)
        if r.returncode == 0:
            return name, "ok", attempt
        tail = (r.stdout + r.stderr)[-1500:]
        if "moderation_blocked" not in tail or attempt == 2:
            return name, "failed: " + tail[-300:].replace("\n", " "), attempt
    return name, "failed", 2
with ThreadPoolExecutor(8) as ex:
    for name, status, attempt in ex.map(lambda kv: run(*kv), NOTES.items()):
        print(f"{time.strftime('%H:%M:%S')} {name}: {status} (attempt {attempt})", flush=True)
