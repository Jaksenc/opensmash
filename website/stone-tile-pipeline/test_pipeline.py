#!/usr/bin/env python3
"""Small deterministic checks for the procedural stone pipeline."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile

import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("stone_generator", HERE / "generate_stone_tile.py")
assert SPEC and SPEC.loader
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


def main() -> None:
    reference = GENERATOR.load_grayscale(GENERATOR.DEFAULT_REFERENCE)
    palette, probabilities = GENERATOR.palette_model(reference)
    first, _ = GENERATOR.generate_candidate(12345, 64, 32, palette, probabilities)
    again, _ = GENERATOR.generate_candidate(12345, 64, 32, palette, probabilities)
    other, _ = GENERATOR.generate_candidate(12346, 64, 32, palette, probabilities)

    assert first.shape == (32, 64)
    assert np.array_equal(first, again), "same seed must be byte-identical"
    assert not np.array_equal(first, other), "different seeds should vary"
    assert set(np.unique(first)).issubset(set(palette))

    four_up = np.tile(first, (2, 2))
    assert np.array_equal(four_up[:32, :64], first)
    assert np.array_equal(four_up[:32, 64:], first)
    assert np.array_equal(four_up[32:, :64], first)
    assert np.array_equal(four_up[32:, 64:], first)

    seam_score, seam = GENERATOR.seam_quality(first)
    assert seam["periodic_generation"] is True
    assert seam["four_up_quadrants_exact"] is True
    assert 0 <= seam_score <= 100

    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "tile.png"
        Image.fromarray(first, mode="L").save(path)
        assert Image.open(path).size == (64, 32)

    svg = GENERATOR.svg_for_tile(first)
    assert '<svg xmlns="http://www.w3.org/2000/svg"' in svg
    assert 'viewBox="0 0 64 32"' in svg
    print("pipeline checks passed")


if __name__ == "__main__":
    main()
