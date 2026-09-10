"""Seeded cuttlefish body-pattern library built on the coherent field noise."""
from __future__ import annotations
from typing import Type
from .field import Field, _smooth_noise, mottle, passing_cloud
from .seed import seed_for

class BodyPattern:
    name: str
    def __init__(self, name: str = ''):
        self.name = name
    def field(self, width: int = 30, height: int = 30, *, seed: int | None = None, t: float = 0.0) -> Field:
        raise NotImplementedError

def _octaves(x: float, y: float, seed: int, scales=(3.0, 7.0, 13.0)) -> float:
    weights = (0.58, 0.28, 0.14)
    return sum(w * _smooth_noise(x / s, y / s, seed + i * 7919) for i, (s, w) in enumerate(zip(scales, weights)))

class UniformFineMottle(BodyPattern):
    def __init__(self): super().__init__('uniform-fine-mottle')
    def field(self, width=30, height=30, *, seed=None, t=0.0):
        return mottle(width, height, seed=seed or 0, scale=1.5, density=.28, grain=.35, contrast=2.0)

class CoarseMottle(BodyPattern):
    def __init__(self): super().__init__('coarse-mottle')
    def field(self, width=30, height=30, *, seed=None, t=0.0):
        return mottle(width, height, seed=seed or 0, scale=5.0, density=.48, grain=.20, contrast=2.0)

class TransverseStripes(BodyPattern):
    def __init__(self): super().__init__('transverse-stripes-zebra')
    def field(self, width=30, height=30, *, seed=None, t=0.0):
        seed = seed or 0; out = Field.blank(width, height)
        for y in range(height):
            band = .5 + .5 * __import__('math').sin(y * .82 + _smooth_noise(0, 0, seed) * 3)
            for x in range(width):
                v = .72 * band + .28 * _smooth_noise(x / 2.5, y / 2.5, seed ^ 31)
                out.set(x, y, max(0, (v - .54) * 2.1))
        return out

class PassingCloudBands(BodyPattern):
    def __init__(self): super().__init__('passing-cloud-bands')
    def field(self, width=30, height=30, *, seed=None, t=0.0):
        base = mottle(width, height, seed=seed or 0, scale=4.0, density=.48, grain=.15, contrast=2.5)
        return passing_cloud(base, t, seed=seed or 0, direction=(0, 1), width_cells=5.0, depth=.9)

class DisruptivePatches(BodyPattern):
    def __init__(self): super().__init__('disruptive-patches')
    def field(self, width=30, height=30, *, seed=None, t=0.0):
        seed = seed or 0; out = Field.blank(width, height)
        for y in range(height):
            for x in range(width):
                coarse = _octaves(x + 4, y, seed, (8, 13, 21))
                fine = _octaves(x, y, seed ^ 0xA53, (1.8, 3.2, 5.0))
                out.set(x, y, .82 if coarse > .57 else (.45 if coarse < .35 else fine * .22))
        return out

class PearlScatter(BodyPattern):
    def __init__(self): super().__init__('pearl-scatter')
    def field(self, width=30, height=30, *, seed=None, t=0.0):
        seed = seed or 0; out = Field.blank(width, height)
        for y in range(height):
            for x in range(width):
                # coherent clusters, thresholded to a measured 10–15% bright fraction
                n = _octaves(x, y, seed, (2.2, 4.0, 7.0))
                out.set(x, y, .95 if n > .68 else .035 * n)
        return out

PATTERN_CLASSES: tuple[Type[BodyPattern], ...] = (UniformFineMottle, CoarseMottle, TransverseStripes, PassingCloudBands, DisruptivePatches, PearlScatter)

def pattern_for(session_id: str) -> BodyPattern:
    return PATTERN_CLASSES[seed_for(session_id) % len(PATTERN_CLASSES)]()

def field_for(session_id: str, width=30, height=30, *, t=0.0) -> tuple[BodyPattern, Field]:
    pattern = pattern_for(session_id)
    return pattern, pattern.field(width, height, seed=seed_for(session_id), t=t)

__all__ = ['BodyPattern', 'UniformFineMottle', 'CoarseMottle', 'TransverseStripes', 'PassingCloudBands', 'DisruptivePatches', 'PearlScatter', 'PATTERN_CLASSES', 'pattern_for', 'field_for']
