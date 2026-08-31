#!/bin/bash
# Cut every character onto every target-fighter skeleton (deterministic,
# no model calls) and stage the results.
script_dir="$(cd "$(dirname "$0")" && pwd)"
project_root="$(dirname "$script_dir")"
cd "$project_root"
set -u
for name in "Barack Obama" "Joey Flynn" "Weird Al Yankovic" "Moritz Baier-Lentz"; do
  echo "SWEEP: START $name"
  if python3 pipeline/run_character.py "$name" --force-stage variants; then
    echo "SWEEP: DONE $name"
  else
    echo "SWEEP: FAILED $name (exit $?)"
  fi
done
echo "SWEEP: ALL COMPLETE"
