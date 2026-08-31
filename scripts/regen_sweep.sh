#!/bin/bash
# Regenerate the demo roster from scratch (post-purge pipeline health check).
# Each character runs the full run_character.py pipeline: expand -> tpose ->
# Tripo mesh/rig -> convert -> portrait -> stock -> emblem -> ui pack -> voice
# -> stage into web-dist/bundles.
script_dir="$(cd "$(dirname "$0")" && pwd)"
project_root="$(dirname "$script_dir")"
cd "$project_root"
set -u

run() {
  local label="$1"; shift
  echo "SWEEP: START $label"
  if python3 pipeline/run_character.py "$@"; then
    echo "SWEEP: DONE $label"
  else
    echo "SWEEP: FAILED $label (exit $?)"
  fi
}

run obama "Barack Obama"
run joeyflynn "Joey Flynn" --photo refs/joey-full.png
run weirdal "Weird Al Yankovic"
run moritz "Moritz Baier-Lentz" --photo refs/moritz-ref.png
echo "SWEEP: ALL COMPLETE"
