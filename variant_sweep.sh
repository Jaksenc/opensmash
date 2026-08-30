#!/bin/bash
# Cut every character onto every target-fighter skeleton (deterministic,
# no model calls) and stage the results.
cd "$(dirname "$0")"
set -u
for name in "Barack Obama" "Joey Flynn" "Weird Al Yankovic" "Moritz Baier-Lentz"; do
  echo "SWEEP: START $name"
  if python3 run_character.py "$name" --force-stage variants; then
    echo "SWEEP: DONE $name"
  else
    echo "SWEEP: FAILED $name (exit $?)"
  fi
done
echo "SWEEP: ALL COMPLETE"
