"""New private constructed coupon, rich across the initial navigation field.

Fixed finite C2 features in specimen metres; no acquisition/view/noise input.
This is a generic analytic specimen, not a calibrated material or measured atlas.
"""
from dataclasses import dataclass
import hashlib
import math
import random
from packages.specimens.bounds_index import build_index
from .human_alignment_specimen import HumanAlignmentSpecimen
from .procedural_specimen import _Feature


def _navigation_features(seed):
    rng = random.Random(int.from_bytes(hashlib.blake2b(
        b'vesm-navigation-coupon-v1:' + seed, digest_size=32).digest(), 'big'))
    result = []
    um = 1e-6
    # Fixed nonperiodic islands. Their jitter,orientation,shape and fine satellites
    # are chosen ONCE; zoom never introduces new texture or repeats a raster tile.
    for row in range(-6, 7):
        for column in range(-6, 7):
            if abs(row) <= 1 and abs(column) <= 1:
                continue  # Preserve the useful original asymmetric alignment mark.
            x = column * .88 + rng.uniform(-.16, .16)
            y = row * .88 + rng.uniform(-.16, .16)
            angle = rng.uniform(-math.pi, math.pi)
            sign = -1. if rng.random() < .42 else 1.
            result.append(_Feature(x*um, y*um, rng.uniform(.32, .60)*um,
                rng.uniform(.24, .48)*um, angle, sign*rng.uniform(.008, .023)*um,
                sign*rng.uniform(.65, 1.15)))
            result.append(_Feature((x+.11)*um, (y-.07)*um,
                rng.uniform(.30, .43)*um, rng.uniform(.24, .35)*um, angle+.6,
                .003*um, .40, 'cross' if (row+column) % 3 else 'ridges',
                rng.uniform(.075, .16)*um, rng.uniform(-math.pi, math.pi)))
            for _ in range(3):
                result.append(_Feature((x+rng.uniform(-.26, .26))*um,
                    (y+rng.uniform(-.25, .25))*um, rng.uniform(.045, .11)*um,
                    rng.uniform(.045, .13)*um, rng.uniform(-math.pi, math.pi),
                    rng.uniform(-.006, .008)*um, rng.uniform(-1., 1.)))
    return tuple(result)


@dataclass(frozen=True)
class MultiscaleAlignmentSpecimen(HumanAlignmentSpecimen):
    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self, '_features', self._features + _navigation_features(self.seed))
        records = tuple((i, math.nextafter(f.x-f.bx, -math.inf),
            math.nextafter(f.y-f.by, -math.inf), math.nextafter(f.x+f.bx, math.inf),
            math.nextafter(f.y+f.by, math.inf)) for i, f in enumerate(self._features))
        object.__setattr__(self, '_bounds_index', build_index(records))
