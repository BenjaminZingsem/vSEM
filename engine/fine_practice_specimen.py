"""Private fixed fine-scale analytic coupon; no view-dependent image generation.

Generic constructed geometry. This is not a measured material/atlas or a live
runtime qualification. Its tighter quadrature must pass convergence/capacity
gates before any human launch can select it.
"""
from dataclasses import dataclass, field
import math
from typing import ClassVar
import numpy as np
from packages.specimens.bounds_index import build_index
from .procedural_specimen import (ProceduralSpecimen, _Feature, RELIEF_LIMIT_M,
    BASE_YIELD, YIELD_SPAN)

MIN_FINE_SUPPORT_RADIUS_M=0.14e-6
MIN_FINE_PATTERN_PERIOD_M=0.24e-6


def _fine_features():
    um=1e-6
    def feature(x,y,rx,ry,angle,height,contrast,kind='particle',period=.24,phase=0.):
        return _Feature(x*um,y*um,rx*um,ry*um,math.radians(angle),height*um,
            contrast,kind,period*um,phase)
    # Distinct finite clusters decorate existing landmarks and a central patch.
    # No repeated global tile,zoom argument,random frame texture or new seed.
    rows=[
        (0.,0.,.22,.17,14,.012,.65),
        (.49,.11,.16,.28,-21,.009,-.52),
        (-.41,.39,.31,.14,67,.014,.46),
        (.13,-.51,.14,.19,5,.008,-.63),
        (-.58,-.24,.19,.23,39,.011,.57),
        (.71,-.36,.28,.16,-43,.015,.41),
        (-1.07,-1.98,.23,.15,27,.010,.63),
        (-.57,-2.27,.14,.25,-33,.009,-.50),
        (-1.42,-1.49,.27,.18,71,.013,.44),
        (9.57,9.89,.18,.29,23,.012,.54),
        (10.13,10.39,.25,.14,-58,.010,-.56),
        (10.52,9.44,.16,.22,39,.014,.61),
        (-10.36,10.31,.20,.15,-17,.012,.48),
        (-9.74,9.68,.14,.27,61,.008,-.60),
        (10.68,-8.27,.23,.16,47,.014,.57),
        (11.23,-7.63,.15,.29,-22,.010,-.45),
    ]
    particles=tuple(feature(*row) for row in rows)
    patterns=(
        feature(.07,.04,1.12,.87,31,.002,.12,'ridges',.24,.36),
        feature(-1.01,-2.02,.96,.78,-19,.0025,.14,'cross',.31,.81),
        feature(10.03,9.98,.83,1.05,63,.002,.13,'ridges',.28,.24),
    )
    return particles+patterns


@dataclass(frozen=True)
class FinePracticeSpecimen(ProceduralSpecimen):
    # Metres. This is a numerical resolution requirement,not optical blur.
    probe_spacing_m: ClassVar[float]=0.02e-6
    _bounds_index: object = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        super().__post_init__()
        extra=_fine_features()
        if any(min(f.rx,f.ry)<MIN_FINE_SUPPORT_RADIUS_M or
            (f.kind in ('ridges','cross') and f.period<MIN_FINE_PATTERN_PERIOD_M) for f in extra):
            raise ValueError('Fine coupon violates its declared construction scales')
        object.__setattr__(self,'_features',self._features+extra)
        # Outward-rounded CLOSED rectangles only select candidates. The original
        # strict analytic support/array predicates below still decide membership.
        records = tuple((i, math.nextafter(f.x-f.bx, -math.inf),
            math.nextafter(f.y-f.by, -math.inf),
            math.nextafter(f.x+f.bx, math.inf),
            math.nextafter(f.y+f.by, math.inf)) for i, f in enumerate(self._features))
        object.__setattr__(self, '_bounds_index', build_index(records))

    def surface(self, x_m, y_m):
        if not math.isfinite(x_m) or not math.isfinite(y_m):
            raise ValueError('finite specimen coordinates required')
        # Retain the original scalar API for NumPy scalars/other finite numeric
        # objects. Only exact float inputs enter the index's narrower API.
        if type(x_m) is float and type(y_m) is float:
            ordinals = self._bounds_index.point(x_m, y_m)
        else:
            ordinals = range(len(self._features))
        z = dx = dy = material = 0.0
        for ordinal in ordinals:
            a, b, c, d = self._features[ordinal].scalar(x_m, y_m)
            z += a; dx += b; dy += c; material += d
        t = math.tanh(z/RELIEF_LIMIT_M)
        return (RELIEF_LIMIT_M*t, (1-t*t)*dx, (1-t*t)*dy,
                BASE_YIELD+YIELD_SPAN*math.tanh(material))

    def surface_arrays(self, x_m, y_m):
        x, y = np.broadcast_arrays(np.asarray(x_m, dtype=np.float64),
                                   np.asarray(y_m, dtype=np.float64))
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError('finite specimen coordinates required')
        z, dx, dy, material = (np.zeros_like(x) for _ in range(4))
        if x.size:
            xmin, xmax, ymin, ymax = float(x.min()), float(x.max()), float(y.min()), float(y.max())
            for ordinal in self._bounds_index.rectangle(xmin, ymin, xmax, ymax):
                f = self._features[ordinal]
                # Preserve the existing vector oracle's coarse and strict masks,
                # including their original binary64 operations/order.
                if xmax < f.x-f.bx or xmin > f.x+f.bx or ymax < f.y-f.by or ymin > f.y+f.by:
                    continue
                mask = (np.abs(x-f.x)<f.bx)&(np.abs(y-f.y)<f.by)
                if not mask.any():
                    continue
                a, b, c, d = f.arrays(x[mask], y[mask])
                z[mask] += a; dx[mask] += b; dy[mask] += c; material[mask] += d
        t = np.tanh(z/RELIEF_LIMIT_M)
        return RELIEF_LIMIT_M*t, (1-t*t)*dx, (1-t*t)*dy, BASE_YIELD+YIELD_SPAN*np.tanh(material)
