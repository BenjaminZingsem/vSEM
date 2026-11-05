"""Private Gaussian cell probabilities; no actor, exposure ledger or public DTO.

Finite numerical regions retain a separate positive tail mass. Integration and
failure parameters were ratified in docs/BEAM_B1A_NUMERICAL_FREEZE.md.
"""
from dataclasses import dataclass, field
import math
import numpy as np
from .beam_profile import Covariance2D

COORDINATE_BOUND_M = .055
CELL_SIZES_M = (25e-9, 12.5e-9, 6.25e-9)
RECTANGLE_ABS_TOL = 2e-16
TAIL_ABS_TOL = 1e-28
REL_TOL = 2e-11
MAX_DEPTH = 20
_SQRT_TWO = math.sqrt(2.0)
_SQRT_TWO_PI = math.sqrt(2.0*math.pi)
_KNOTS = (-12.0, -8.0, -4.0, 0.0, 4.0, 8.0, 12.0)
_RULES = tuple(tuple(zip(map(float, x), map(float, w)))
               for x, w in (np.polynomial.legendre.leggauss(16),
                            np.polynomial.legendre.leggauss(32)))


class NumericalConvergenceError(ValueError):
    """A numerical result cannot satisfy the frozen convergence envelope."""


def _real(value, low, high, name):
    if type(value) not in (int, float) or not low <= value <= high:
        raise ValueError(name+' outside finite numerical envelope')
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(name+' must be finite') from error
    if not math.isfinite(result):
        raise ValueError(name+' must be finite')
    return result


def _coordinate(value):
    return _real(value, -COORDINATE_BOUND_M, COORDINATE_BOUND_M, 'coordinate')


def _covariance(value):
    if type(value) is not Covariance2D:
        raise ValueError('exact Covariance2D required')
    low, high = value.principal_variances_m2()
    if math.sqrt(low) < 5e-9 or math.sqrt(high) > 200e-9:
        raise ValueError('principal RMS outside 5..200 nm')
    conditional = (value.xx_m2*value.yy_m2-value.xy_m2**2)/value.xx_m2
    if not math.isfinite(conditional) or conditional <= 0:
        raise ValueError('positive finite conditional variance required')
    return value


def _mass(value):
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise NumericalConvergenceError('invalid Gaussian probability')
    return value


def _normal_interval(a, b):
    if b < a:
        raise ValueError('reversed standard normal interval')
    if a >= 0:
        result = .5*(math.erfc(a/_SQRT_TWO)-math.erfc(b/_SQRT_TWO))
    elif b <= 0:
        result = .5*(math.erfc(-b/_SQRT_TWO)-math.erfc(-a/_SQRT_TWO))
    else:
        result = .5*(math.erf(b/_SQRT_TWO)-math.erf(a/_SQRT_TWO))
    return _mass(result)


def _normal_outside(a, b):
    return _mass(.5*math.erfc(-a/_SQRT_TWO)+.5*math.erfc(b/_SQRT_TWO))


def _panel(function, left, right, rule):
    middle = left+(right-left)*.5
    half = (right-left)*.5
    terms = []
    for node, weight in rule:
        value = function(middle+half*node)
        if not math.isfinite(value) or value < 0:
            raise NumericalConvergenceError('invalid Gaussian integrand')
        terms.append(weight*value)
    result = half*math.fsum(terms)
    if not math.isfinite(result) or result < 0:
        raise NumericalConvergenceError('invalid Gaussian integral')
    return result


def _adaptive(function, left, right, abs_tol, depth=0):
    first = _panel(function, left, right, _RULES[0])
    second = _panel(function, left, right, _RULES[1])
    error = abs(second-first)
    if error <= max(abs_tol, REL_TOL*abs(second)):
        return second, error
    middle = left+(right-left)*.5
    if depth >= MAX_DEPTH or middle in (left, right):
        raise NumericalConvergenceError('Gaussian integration did not converge')
    a, ea = _adaptive(function, left, middle, abs_tol*.5, depth+1)
    b, eb = _adaptive(function, middle, right, abs_tol*.5, depth+1)
    return math.fsum((a,b)), math.fsum((ea,eb))


def _integral(function, left, right, abs_tol):
    if left == right:
        return 0.0, 0.0
    cuts = (left,)+tuple(k for k in _KNOTS if left < k < right)+(right,)
    values, errors = [], []
    for a,b in zip(cuts,cuts[1:]):
        value, error = _adaptive(function,a,b,abs_tol/(len(cuts)-1))
        values.append(value); errors.append(error)
    return math.fsum(values), math.fsum(errors)


def _rectangle(covariance, cx, cy, x0, x1, y0, y1, outside=False):
    sx, sy = math.sqrt(covariance.xx_m2), math.sqrt(covariance.yy_m2)
    a, b = (x0-cx)/sx, (x1-cx)/sx
    if covariance.xy_m2 == 0.0:
        ylower, yupper = (y0-cy)/sy, (y1-cy)/sy
        xinside = _normal_interval(a,b)
        if outside:
            return _mass(math.fsum((_normal_outside(a,b),
                                   xinside*_normal_outside(ylower,yupper)))), 0.0
        return _mass(xinside*_normal_interval(ylower,yupper)), 0.0
    conditional = math.sqrt((covariance.xx_m2*covariance.yy_m2-
                             covariance.xy_m2**2)/covariance.xx_m2)
    shift = covariance.xy_m2/sx/conditional
    ylower, yupper = (y0-cy)/conditional, (y1-cy)/conditional
    def integrand(u):
        lo, hi = ylower-shift*u, yupper-shift*u
        probability = _normal_outside(lo,hi) if outside else _normal_interval(lo,hi)
        return math.exp(-.5*u*u)/_SQRT_TWO_PI*probability
    result, error = _integral(integrand,a,b,TAIL_ABS_TOL if outside else RECTANGLE_ABS_TOL)
    if outside:
        result = math.fsum((_normal_outside(a,b),result))
    return _mass(result), error


def rectangle_probability(covariance, center_x_m, center_y_m,
                          x0_m, x1_m, y0_m, y1_m):
    covariance = _covariance(covariance)
    cx,cy,x0,x1,y0,y1 = map(_coordinate,
        (center_x_m,center_y_m,x0_m,x1_m,y0_m,y1_m))
    if x1 < x0 or y1 < y0:
        raise ValueError('reversed Gaussian rectangle')
    if x1 == x0 or y1 == y0:
        return 0.0
    return _rectangle(covariance,cx,cy,x0,x1,y0,y1)[0]


@dataclass(frozen=True)
class FluenceCell:
    index_x: int
    index_y: int
    probability: float

    def __post_init__(self):
        if type(self.index_x) is not int or type(self.index_y) is not int:
            raise ValueError('exact cell indices required')
        if type(self.probability) is not float or not 0 < self.probability <= 1:
            raise ValueError('positive finite cell probability required')


@dataclass(frozen=True)
class PrimaryFluence:
    center_x_m: float
    center_y_m: float
    cell_size_m: float
    covariance: Covariance2D
    cells: tuple
    box_edges_m: tuple
    tail_probability: float
    normalization_correction: float
    estimated_error: float
    protocol: str = field(default='vsem.primary-fluence.v1',init=False)

    def __post_init__(self):
        _coordinate(self.center_x_m); _coordinate(self.center_y_m)
        _covariance(self.covariance)
        if type(self.cell_size_m) is not float or self.cell_size_m not in CELL_SIZES_M:
            raise ValueError('qualified cell size required')
        if type(self.cells) is not tuple or not self.cells or any(type(c) is not FluenceCell for c in self.cells):
            raise ValueError('immutable positive cell tuple required')
        indices = tuple((c.index_y,c.index_x) for c in self.cells)
        if indices != tuple(sorted(set(indices))):
            raise ValueError('unique row-major cells required')
        if type(self.box_edges_m) is not tuple or len(self.box_edges_m) != 4:
            raise ValueError('immutable cell box required')
        x0,x1,y0,y1 = map(_coordinate,self.box_edges_m)
        if x0 >= x1 or y0 >= y1:
            raise ValueError('positive cell box required')
        _real(self.tail_probability,0.0,1.0,'tail')
        _real(self.normalization_correction,-5e-11,5e-11,'normalization correction')
        _real(self.estimated_error,0.0,1.0,'error estimator')
        if abs(math.fsum(c.probability for c in self.cells)+self.tail_probability-1.0) > 8e-15:
            raise NumericalConvergenceError('Gaussian probability closure failed')


def primary_fluence(covariance, center_x_m, center_y_m, *, cell_size_m=25e-9):
    covariance = _covariance(covariance)
    cx,cy = _coordinate(center_x_m), _coordinate(center_y_m)
    if type(cell_size_m) is not float or cell_size_m not in CELL_SIZES_M:
        raise ValueError('qualified cell size required')
    sx,sy = math.sqrt(covariance.xx_m2),math.sqrt(covariance.yy_m2)
    ix0,ix1 = math.floor((cx-8*sx)/cell_size_m),math.ceil((cx+8*sx)/cell_size_m)
    iy0,iy1 = math.floor((cy-8*sy)/cell_size_m),math.ceil((cy+8*sy)/cell_size_m)
    box = tuple(_coordinate(v*cell_size_m) for v in (ix0,ix1,iy0,iy1))
    if (box[0] > cx-8*sx or box[1] < cx+8*sx or
            box[2] > cy-8*sy or box[3] < cy+8*sy):
        raise NumericalConvergenceError('cell box does not enclose eight sigma')
    tail, tail_error = _rectangle(covariance,cx,cy,*box,outside=True)
    rows, errors = [], [tail_error]
    for iy in range(iy0,iy1):
        for ix in range(ix0,ix1):
            probability,error = _rectangle(covariance,cx,cy,ix*cell_size_m,
                (ix+1)*cell_size_m,iy*cell_size_m,(iy+1)*cell_size_m)
            errors.append(error)
            if probability:
                rows.append((ix,iy,probability))
    total = math.fsum(p for _,_,p in rows)
    if total <= 0 or not math.isfinite(total):
        raise NumericalConvergenceError('nonpositive Gaussian inside mass')
    scale = (1.0-tail)/total
    if not math.isfinite(scale) or abs(scale-1.0) > 5e-11:
        raise NumericalConvergenceError('Gaussian normalization correction exceeded')
    cells = tuple(FluenceCell(ix,iy,p*scale) for ix,iy,p in rows)
    return PrimaryFluence(cx,cy,cell_size_m,covariance,cells,box,tail,
                          scale-1.0,math.fsum(errors))
