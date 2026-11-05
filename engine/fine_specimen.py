"""Private fixed-coordinate fine coupon candidate, not measured material truth.

Macro geometry is reused unchanged. Compact C2 windows have Fourier tails;
100 nm relief and >=500 nm composition refer to carriers, not bandlimits.
"""
from dataclasses import dataclass, field
import math
import numpy as np
from engine.procedural_specimen import ProceduralSpecimen

FINE_AMPLITUDE_M = 2e-9
FINE_CARRIER_M = 100e-9
HEIGHT_BOUND_M = .552e-6
COORDINATE_BOUND_M = .055


def _coordinate(value):
    if type(value) not in (int, float) or not -COORDINATE_BOUND_M <= value <= COORDINATE_BOUND_M:
        raise ValueError('finite builtin specimen coordinate within +/-0.055 m required')
    return float(value)


def _array(value):
    if isinstance(value, (bool, np.bool_)):
        raise ValueError('boolean coordinates are not real coordinates')
    if isinstance(value, (tuple, list)):
        # Reject mixed bool/real sequences before NumPy erases bool identity.
        def boolean(item):
            return (isinstance(item, (bool, np.bool_)) or
                    isinstance(item, (tuple, list)) and any(boolean(v) for v in item))
        if boolean(value):
            raise ValueError('boolean coordinates are not real coordinates')
    original = np.asarray(value)
    if original.dtype.kind not in 'fiu':
        raise ValueError('real numeric coordinate dtype required')
    result = np.asarray(original, dtype=np.float64)
    if not np.isfinite(result).all() or np.any(np.abs(result) > COORDINATE_BOUND_M):
        raise ValueError('finite specimen coordinate within +/-0.055 m required')
    return result


@dataclass(frozen=True)
class _Patch:
    x_m: float
    y_m: float
    radius_m: float
    angle_rad: float
    phase_rad: float
    period_m: float
    amplitude: float
    c: float = field(init=False, repr=False)
    s: float = field(init=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, 'c', math.cos(self.angle_rad))
        object.__setattr__(self, 's', math.sin(self.angle_rad))

    def scalar(self, x, y, relief=False, bse=False):
        dx, dy = x-self.x_m, y-self.y_m
        r = math.hypot(dx, dy) / self.radius_m
        if r >= 1.0:
            return (0.0, 0.0, 0.0) if relief else 0.0
        w = (1-r)**4 * (4*r+1)
        k = 2.0 * math.pi / self.period_m
        phase = k*(self.c*dx+self.s*dy) + self.phase_rad
        wave = math.sin(phase)
        if not relief:
            return self.amplitude*w*(.6+.4*wave if bse else wave)
        derivative = -20.0 * (1-r)**3 / self.radius_m**2
        factor = k * math.cos(phase)
        return (self.amplitude*w*wave,
                self.amplitude*(derivative*dx*wave + w*factor*self.c),
                self.amplitude*(derivative*dy*wave + w*factor*self.s))

    def arrays(self, x, y, relief=False, bse=False):
        dx, dy = x-self.x_m, y-self.y_m
        r = np.hypot(dx, dy) / self.radius_m
        a = np.maximum(0.0, 1-r)
        w = a**4 * (4*r+1)
        k = 2.0 * math.pi / self.period_m
        phase = k*(self.c*dx+self.s*dy) + self.phase_rad
        wave = np.sin(phase)
        if not relief:
            return self.amplitude*w*(.6+.4*wave if bse else wave)
        derivative = -20.0*a**3/self.radius_m**2
        factor = k*np.cos(phase)
        return (self.amplitude*w*wave,
                self.amplitude*(derivative*dx*wave + w*factor*self.c),
                self.amplitude*(derivative*dy*wave + w*factor*self.s))


def _patch(x, y, radius, angle, phase, period, amplitude):
    return _Patch(x*1e-6, y*1e-6, radius*1e-6, math.radians(angle),
                  phase, period*1e-6, amplitude)


_FINE_PATCHES = tuple(_patch(x, y, r, angle, phase, .1, FINE_AMPLITUDE_M)
                      for x,y,r,angle,phase in ((-.30,0,.28,0,.3),(.30,0,.28,90,-.4),
                      (10,10,1.6,27,.7),(-12,10,1.4,-10,-.2),(11,-8,1.5,24,.5)))
_SE_PATCHES = (_patch(0,0,3,17,.1,.75,.5), _patch(10,10,4,35,.4,1,.5),
               _patch(-12,10,3,73,.2,.5,.5))
_BSE_PATCHES = (_patch(12,-8,5,20,-.3,.9,1.2), _patch(-11,10,5,-35,.7,.6,-.9),
                _patch(0,0,3,63,.5,.5,.5))


@dataclass(frozen=True)
class SpecimenBounds:
    height_abs_m: float
    slope_magnitude: float
    fine_height_abs_m: float
    fine_slope_magnitude: float
    shortest_relief_carrier_m: float
    shortest_composition_carrier_m: float


@dataclass(frozen=True)
class FineSpecimen:
    seed: bytes = field(default=b'vesm-fine-procedural-coupon-v1', repr=False)
    specimen_id: str = field(default='vsem.fine-procedural-coupon.v1', init=False)
    calibration_status: str = field(default='generic_uncalibrated', init=False)
    _macro: ProceduralSpecimen = field(init=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, '_macro', ProceduralSpecimen(self.seed))

    def surface(self, x_m, y_m):
        x, y = _coordinate(x_m), _coordinate(y_m)
        height, sx, sy, macro_yield = self._macro.surface(x, y)
        for patch in _FINE_PATCHES:
            z, dx, dy = patch.scalar(x, y, relief=True)
            height += z; sx += dx; sy += dy
        se_phase = (macro_yield-.22)/.10 + math.fsum(p.scalar(x,y) for p in _SE_PATCHES)
        bse_phase = math.fsum(p.scalar(x,y,bse=True) for p in _BSE_PATCHES)
        return height, sx, sy, .30+.06*math.tanh(se_phase), .22+.08*math.tanh(bse_phase)

    def surface_arrays(self, x_m, y_m):
        x, y = np.broadcast_arrays(_array(x_m), _array(y_m))
        height, sx, sy, macro_yield = (np.array(v,dtype=np.float64,copy=True)
                                      for v in self._macro.surface_arrays(x,y))
        se_phase = np.array((macro_yield-.22)/.10,dtype=np.float64)
        bse_phase = np.zeros_like(x)
        for patches, mode in ((_FINE_PATCHES,'relief'),(_SE_PATCHES,'SE'),(_BSE_PATCHES,'BSE')):
            for patch in patches:
                mask = (np.abs(x-patch.x_m)<patch.radius_m)&(np.abs(y-patch.y_m)<patch.radius_m)
                if not mask.any():
                    continue
                if mode == 'relief':
                    z, dx, dy = patch.arrays(x[mask],y[mask],relief=True)
                    height[mask] += z; sx[mask] += dx; sy[mask] += dy
                elif mode == 'SE':
                    se_phase[mask] += patch.arrays(x[mask],y[mask])
                else:
                    bse_phase[mask] += patch.arrays(x[mask],y[mask],bse=True)
        return (height, sx, sy, np.asarray(.30+.06*np.tanh(se_phase)),
                np.asarray(.22+.08*np.tanh(bse_phase)))

    def bounds(self):
        macro = 0.0
        for feature in self._macro._features:
            derivative = 2.109375/min(feature.rx, feature.ry)
            if feature.kind in ('ridges','cross'):
                derivative += 2.0*math.pi/feature.period*(1.73 if feature.kind=='cross' else 1.0)
            elif feature.kind == 'terrace':
                derivative += .5/feature.step_width
            macro += abs(feature.height)*derivative
        fine = FINE_AMPLITUDE_M*(2.109375/min(p.radius_m for p in _FINE_PATCHES) +
                                 2.0*math.pi/FINE_CARRIER_M)
        return SpecimenBounds(HEIGHT_BOUND_M, macro+fine,
                              FINE_AMPLITUDE_M, fine, FINE_CARRIER_M,
                              min(p.period_m for p in _SE_PATCHES+_BSE_PATCHES))
