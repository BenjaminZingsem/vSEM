"""Private, frontier-owned reduced SE physics; no public transport or asset API.

Assumptions and limitations are frozen in docs/CAUSAL_SLICE.md. Inputs use SI.
"""
from dataclasses import dataclass
import hashlib
import math
import random
from statistics import NormalDist
from collections import OrderedDict
import os
import numpy as np
from .specimen_material import SpecimenMaterial,LEGACY_HISTORY_PROXY

NUMPY_VERSION = '1.26.4'
if np.__version__ != NUMPY_VERSION:
    raise RuntimeError('reference physics requires qualified NumPy '+NUMPY_VERSION)

E_CHARGE = 1.602176634e-19
CURRENT_A = 1e-11
CELL_M = 0.25e-6


@dataclass(frozen=True)
class AppliedSettings:
    x_m: float = 0.0
    y_m: float = 0.0
    focus_m: float = 0.0
    stig_x: float = 0.0
    stig_y: float = 0.0


def probe_axes(focus_m, stig_x, stig_y, height_m=0.0):
    """Two orthogonal focal planes; rotation is half the stigmator phase."""
    a, b = (stig_x - 0.18) * 3e-6, (stig_y + 0.12) * 3e-6
    astig = math.hypot(a, b)
    defocus = focus_m - 1.2e-6 + height_m
    base, aperture = 0.035e-6, 0.06
    return (math.hypot(base, aperture * (defocus - astig)),
            math.hypot(base, aperture * (defocus + astig)),
            0.5 * math.atan2(b, a))


def probe_points(settings, x_m, y_m, height_m=0.0, max_spacing_m=0.10e-6):
    if type(max_spacing_m) not in (float,int) or not math.isfinite(max_spacing_m) or not 0<max_spacing_m<=0.10e-6:
        raise ValueError('Positive bounded probe quadrature spacing required')
    sx, sy, angle = probe_axes(settings.focus_m, settings.stig_x, settings.stig_y, height_m)
    c, s = math.cos(angle), math.sin(angle)
    def axis(sigma):
        # Physical spacing bounds prevent sigma-spaced quadrature from
        # recreating specimen harmonics under defocus. Truncate at 4.5 sigma.
        count = math.ceil(4.5*sigma/min(sigma,max_spacing_m))
        offsets = [i*4.5*sigma/count for i in range(-count,count+1)]
        weights = [math.exp(-0.5*(p/sigma)**2) for p in offsets]
        norm = math.fsum(weights)
        return tuple((p,w/norm) for p,w in zip(offsets,weights))
    return tuple((x_m+c*px-s*py,y_m+s*px+c*py,wx*wy)
                 for px,wx in axis(sx) for py,wy in axis(sy))


def surface(x, y):
    """Analytic relief, slope and material yield, with bounded smooth features."""
    pitch = 12e-6
    radius, height = 2e-6, 0.65e-6
    k = 2*math.pi/pitch
    a = (1/(k*radius))**2
    g = math.exp(a*(math.cos(k*x)+math.cos(k*y)-2))
    # A grating supplies orthogonal focus/stigmation features; never a truth map.
    frequency = 2*math.pi/1.5e-6
    z = height*g + 0.06e-6*math.sin(frequency*x)*math.cos(frequency*y)
    dx = -height*g*a*k*math.sin(k*x) + 0.06e-6*frequency*math.cos(frequency*x)*math.cos(frequency*y)
    dy = -height*g*a*k*math.sin(k*y) - 0.06e-6*frequency*math.sin(frequency*x)*math.sin(frequency*y)
    base = 0.22 + 0.09*g
    return z, dx, dy, base


class ScalarSpecimenHistory:
    """Persistent sparse specimen cells. Lazy relaxation is observer-independent."""
    def __init__(self, specimen=None, material=None):
        # Trusted constructor-only source; analytic fixture remains the default.
        self._specimen = specimen
        spacing=getattr(specimen,'probe_spacing_m',0.10e-6)
        if type(spacing) not in (float,int) or not math.isfinite(spacing) or not 0<spacing<=0.10e-6:
            raise ValueError('Trusted source quadrature spacing required')
        self._probe_spacing_m=float(spacing)
        if material is not None and type(material) is not SpecimenMaterial:
            raise ValueError('trusted material boundary required')
        self._material=LEGACY_HISTORY_PROXY if material is None else material
        self._cells = {}
        self.total_charge_C = 0.0

    def _surface(self, x, y):
        return surface(x, y) if self._specimen is None else self._specimen.surface(x, y)

    def expose(self, x, y, start_s, end_s, charge_C):
        key = (math.floor(x/CELL_M), math.floor(y/CELL_M))
        dose, potential, previous = self._cells.get(key, (0.0, 0.0, start_s))
        if start_s < previous - 1e-12 or end_s < start_s or charge_C < 0:
            raise ValueError('history cannot rewind')
        potential = 0.0 if self._material.grounded else potential*math.exp(-max(0.0, start_s-previous)/2.0)
        interval = end_s-start_s
        # Negative surface potential for net electron retention. Linear RC proxy.
        retained = charge_C*0.015/1e-17
        if self._material.grounded:
            final_v = 0.0
        elif interval:
            decay = math.exp(-interval/2.0)
            final_v = potential*decay - retained*(1-decay)/(interval/2.0)
        else:
            final_v = potential-retained
        scale=self._material.damage_charge_scale_C
        attenuation = 1.0 if scale is None else math.exp(-dose/scale)
        if charge_C and scale is not None:
            attenuation *= -math.expm1(-charge_C/scale)/(charge_C/scale)
        signal_factor = attenuation / (1 + abs((potential+final_v)/2)*0.02)
        deflection_m = max(-0.3e-6, min(0.3e-6, potential*1e-9))
        self._cells[key] = (dose+charge_C, final_v, end_s)
        self.total_charge_C += charge_C
        return signal_factor, deflection_m

    def response(self, settings, x, y, start_s):
        """Hold response for one pixel/settings interval, never an observer tick.

        This declared left-endpoint discretization is independent of UI polling;
        the RC/dose state still evolves through all dwell. Physical interval
        convergence is a later gate for the broader reduced model.
        """
        z, _, _, _ = self._surface(x, y)
        # Multiple quadrature points can land in one lattice cell. Coalesce first
        # so each physical cell evolves once for this exposure interval.
        cells = {}
        for px, py, weight in probe_points(settings, x, y, z,self._probe_spacing_m):
            key = (math.floor(px/CELL_M), math.floor(py/CELL_M))
            cells.setdefault(key, []).append((px, py, weight))
        response = []
        for key, points in cells.items():
            w = math.fsum(p[2] for p in points)
            dose, potential, previous = self._cells.get(key, (0.0, 0.0, start_s))
            potential = 0.0 if self._material.grounded else potential*math.exp(-max(0.0,start_s-previous)/2.0)
            scale=self._material.damage_charge_scale_C
            factor = (1.0 if scale is None else math.exp(-dose/scale))/(1+abs(potential)*0.02)
            drift = max(-0.3e-6, min(0.3e-6, potential*1e-9))
            signal = 0.0
            for px, py, weight in points:
                _, dx, dy, base = self._surface(px+drift, py)
                yield_se = base*math.sqrt(1+dx*dx+dy*dy)*(1+0.12*dx/math.sqrt(1+dx*dx))
                signal += weight*yield_se*factor
            response.append((points[0][0], points[0][1], w, signal))
        return tuple(response)

    def expectation(self, response, start_s, end_s):
        charge = CURRENT_A*(end_s-start_s)
        for px, py, weight, signal in response:
            self.expose(px, py, start_s, end_s, charge*weight)
        return charge/E_CHARGE * math.fsum(item[3] for item in response) * 0.35


def available_memory_bytes():
    """Actual currently available host memory; no model/RAM resource restriction."""
    if os.name == 'nt':
        import ctypes
        class MemoryStatus(ctypes.Structure):
            _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in ('total', 'available', 'page_total',
                    'page_available', 'virtual_total', 'virtual_available', 'extended')]
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise RuntimeError('cannot measure reference cache memory availability')
        return status.available
    return os.sysconf('SC_AVPHYS_PAGES')*os.sysconf('SC_PAGE_SIZE')


@dataclass(frozen=True)
class ProbeResponse:
    template: tuple
    signals: object

    def __iter__(self):
        _, _, _, _, first_x, first_y, weights, _ = self.template
        return iter(zip(first_x, first_y, weights, self.signals))


class SpecimenHistory(ScalarSpecimenHistory):
    """Same scalar physical law, vectorized immutable quadrature and surface.

    ScalarSpecimenHistory remains the independent reference solver.
    Templates cache coordinates/weights only. Dose, potential relaxation and
    drifted surface yield are recomputed from current cells every interval.
    Cache is LRU with one quarter of measured available RAM; eviction changes
    computation cost only. Float64 reduction follows original point/group order.
    """
    def __init__(self, cache_bytes=None, specimen=None, material=None):
        super().__init__(specimen=specimen,material=material)
        self.cache_limit_bytes = available_memory_bytes()//4 if cache_bytes is None else cache_bytes
        if type(self.cache_limit_bytes) is not int or self.cache_limit_bytes <= 0:
            raise ValueError('positive reference cache memory required')
        self._templates = OrderedDict()
        self._template_bytes = 0

    def _template(self, settings, x, y):
        key = settings, x, y
        cached = self._templates.get(key)
        if cached is not None:
            self._templates.move_to_end(key)
            return cached
        z, _, _, _ = self._surface(x,y)
        sx, sy, angle = probe_axes(settings.focus_m,settings.stig_x,settings.stig_y,z)
        c,s = math.cos(angle),math.sin(angle)
        def axis(sigma):
            count = math.ceil(4.5*sigma/min(sigma,self._probe_spacing_m))
            positions = np.arange(-count,count+1,dtype=np.float64)*4.5*sigma/count
            # math.exp/fsum retain the scalar normalization arithmetic exactly.
            weights = np.array([math.exp(-.5*(float(p)/sigma)**2) for p in positions])
            weights /= math.fsum(weights)
            return positions, weights
        ax,wx = axis(sx); ay,wy = axis(sy)
        px = (x+c*ax[:,None]-s*ay[None,:]).ravel()
        py = (y+s*ax[:,None]+c*ay[None,:]).ravel()
        weights = (wx[:,None]*wy[None,:]).ravel()
        cell_x = np.floor(px/CELL_M).astype(np.int64)
        cell_y = np.floor(py/CELL_M).astype(np.int64)
        groups, unique, inverse = {}, [], np.empty(px.size,dtype=np.intp)
        first = []
        for index,pair in enumerate(zip(cell_x,cell_y)):
            cell = int(pair[0]),int(pair[1])
            group = groups.get(cell)
            if group is None:
                group = len(unique); groups[cell] = group; unique.append(cell); first.append(index)
            inverse[index] = group
        first = np.array(first,dtype=np.intp)
        grouped = [[] for _ in unique]
        for group,weight in zip(inverse,weights): grouped[group].append(float(weight))
        group_weights = np.array([math.fsum(part) for part in grouped])
        arrays = px,py,weights,inverse,px[first],py[first],group_weights
        for item in arrays: item.setflags(write=False)
        template = (*arrays, tuple(unique))
        size = sum(item.nbytes for item in arrays)+len(unique)*128
        # An oversized template can still be computed; it is simply uncached.
        if size <= self.cache_limit_bytes:
            while self._templates and self._template_bytes+size > self.cache_limit_bytes:
                _,removed = self._templates.popitem(last=False)
                self._template_bytes -= sum(item.nbytes for item in removed[:-1])+len(removed[-1])*128
            self._templates[key] = template
            self._template_bytes += size
        return template

    def response(self, settings, x, y, start_s):
        template = self._template(settings,x,y)
        px,py,weights,inverse,_,_,_,keys = template
        factors = np.empty(len(keys)); drifts = np.empty(len(keys))
        for index,key in enumerate(keys):
            dose,potential,previous = self._cells.get(key,(0.0,0.0,start_s))
            potential = 0.0 if self._material.grounded else potential*math.exp(-max(0.0,start_s-previous)/2.0)
            scale=self._material.damage_charge_scale_C
            factors[index] = (1.0 if scale is None else math.exp(-dose/scale))/(1+abs(potential)*.02)
            drifts[index] = max(-.3e-6,min(.3e-6,potential*1e-9))
        shifted_x = px+drifts[inverse]
        if self._specimen is not None:
            _,dx,dy,base = self._specimen.surface_arrays(shifted_x,py)
        else:
            pitch,radius,height = 12e-6,2e-6,.65e-6
            k = 2*math.pi/pitch; a = (1/(k*radius))**2
            frequency = 2*math.pi/1.5e-6
            g = np.exp(a*(np.cos(k*shifted_x)+np.cos(k*py)-2))
            dx = -height*g*a*k*np.sin(k*shifted_x)+.06e-6*frequency*np.cos(frequency*shifted_x)*np.cos(frequency*py)
            dy = -height*g*a*k*np.sin(k*py)-.06e-6*frequency*np.sin(frequency*shifted_x)*np.sin(frequency*py)
            base = .22+.09*g
        yield_se = base*np.sqrt(1+dx*dx+dy*dy)*(1+.12*dx/np.sqrt(1+dx*dx))
        signals = np.bincount(inverse,weights=weights*yield_se*factors[inverse],minlength=len(keys))
        signals.setflags(write=False)
        return ProbeResponse(template,signals)

    def expectation(self, response, start_s, end_s):
        if not isinstance(response,ProbeResponse):
            return super().expectation(response,start_s,end_s)
        charge = CURRENT_A*(end_s-start_s)
        weights,keys = response.template[6:]
        interval = end_s-start_s
        decay = math.exp(-interval/2.0) if interval else 1.0
        for key,weight in zip(keys,weights):
            part = charge*float(weight)
            dose,potential,previous = self._cells.get(key,(0.0,0.0,start_s))
            if start_s < previous-1e-12 or end_s < start_s or part < 0:
                raise ValueError('history cannot rewind')
            potential = 0.0 if self._material.grounded else potential*math.exp(-max(0.0,start_s-previous)/2.0)
            retained = part*.015/1e-17
            final_v = 0.0 if self._material.grounded else (potential*decay-retained*(1-decay)/(interval/2.0) if interval else potential-retained)
            self._cells[key] = dose+part,final_v,end_s
            self.total_charge_C += part
        return charge/E_CHARGE*math.fsum(response.signals)*.35


def detector_count(seed, capture_id, pixel_index, expectation):
    """Order-independent private random key; Gaussian approximation for large mean."""
    key = hashlib.blake2b(seed + capture_id.encode() + pixel_index.to_bytes(8, 'big'), digest_size=16).digest()
    rng = random.Random(int.from_bytes(key, 'big'))
    if expectation <= 0:
        return 0
    # Couple generations through one quantile: a growing partial pixel must
    # never lose previously counted electrons. Direct inverse CDF below 50;
    # a monotone normal approximation, anchored at the boundary, above 50.
    quantile = min(1-2**-53,max(2**-53,rng.random()))
    mean = min(expectation,50.0)
    probability = cumulative = math.exp(-mean)
    count = 0
    while cumulative < quantile:
        count += 1
        probability *= mean/count
        cumulative += probability
    if expectation <= 50:
        return count
    z = NormalDist().inv_cdf(quantile)
    return max(count,round(expectation+math.sqrt(expectation)*z))
