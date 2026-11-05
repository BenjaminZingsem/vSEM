"""Private B0 generic Gaussian beam candidate; no runtime capability is enabled.

SI equations and equivalent-diameter assumptions are frozen in
docs/BEAM_B0_NUMERICAL_FREEZE.md. This is not a calibrated instrument model.
"""
from dataclasses import dataclass, field
import math

ELEMENTARY_CHARGE_C = 1.602176634e-19
PLANCK_J_S = 6.62607015e-34
LIGHT_SPEED_M_S = 299792458.0
ELECTRON_MASS_KG = 9.1093837139e-31
HEIGHT_BOUND_M = 0.552e-6
DIAMETER_TO_SIGMA = 2.0 * math.sqrt(2.0 * math.log(2.0))


def _real(value, lower, upper, name):
    if type(value) not in (int, float) or not lower <= value <= upper:
        raise ValueError(name + ' outside numerical envelope')
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(name + ' must be finite')
    return number


def electron_wavelength_m(kinetic_energy_eV):
    energy = _real(kinetic_energy_eV, 1000.0, 20000.0, 'energy_eV')
    kinetic = ELEMENTARY_CHARGE_C * energy
    return PLANCK_J_S / math.sqrt(
        2.0 * ELECTRON_MASS_KG * kinetic *
        (1.0 + kinetic / (2.0 * ELECTRON_MASS_KG * LIGHT_SPEED_M_S**2)))


@dataclass(frozen=True)
class BeamSettings:
    current_A: float = 1e-11
    focus_offset_m: float = 0.0
    stigmator_x: float = 0.0
    stigmator_y: float = 0.0

    def __post_init__(self):
        for name, low, high in (('current_A', 1e-12, 1e-9),
                                ('focus_offset_m', -25e-6, 25e-6),
                                ('stigmator_x', -1.0, 1.0),
                                ('stigmator_y', -1.0, 1.0)):
            object.__setattr__(self, name, _real(getattr(self, name), low, high, name))


@dataclass(frozen=True)
class BlurComponents:
    wavelength_m: float
    source_diameter_m: float
    diffraction_diameter_m: float
    spherical_diameter_m: float
    chromatic_diameter_m: float
    sigma_base_m: float


@dataclass(frozen=True)
class Covariance2D:
    xx_m2: float
    xy_m2: float
    yy_m2: float

    def __post_init__(self):
        for name in ('xx_m2', 'xy_m2', 'yy_m2'):
            object.__setattr__(self, name, _real(getattr(self, name), -1.0, 1.0, name))
        if (self.xx_m2 <= 0 or self.yy_m2 <= 0 or
                self.xx_m2 * self.yy_m2 - self.xy_m2**2 <= 0):
            raise ValueError('positive-definite covariance required')

    def principal_variances_m2(self):
        high = .5 * (self.xx_m2 + self.yy_m2 +
                     math.hypot(self.xx_m2 - self.yy_m2, 2.0 * self.xy_m2))
        low = (self.xx_m2 * self.yy_m2 - self.xy_m2**2) / high
        return low, high

    def transfer(self, frequency_x_per_m, frequency_y_per_m):
        fx = _real(frequency_x_per_m, -1e8, 1e8, 'frequency_x')
        fy = _real(frequency_y_per_m, -1e8, 1e8, 'frequency_y')
        if math.hypot(fx, fy) > 1e8:
            raise ValueError('frequency norm outside numerical envelope')
        variance = self.xx_m2 * fx**2 + 2.0 * self.xy_m2 * fx * fy + self.yy_m2 * fy**2
        return math.exp(-2.0 * math.pi**2 * variance)


@dataclass(frozen=True)
class BeamProfile:
    profile_id: str = field(default='generic-fe-sem-grounded-v2', init=False)
    optics_id: str = field(default='vsem.gaussian-probe.v2', init=False)
    calibration_status: str = field(default='generic_uncalibrated', init=False)
    energy_eV: float = field(default=5000.0, init=False)
    working_distance_m: float = field(default=.010, init=False)
    semiangle_rad: float = field(default=.005, init=False)
    reduced_brightness: float = field(default=1e7, init=False)
    energy_spread_eV: float = field(default=.5, init=False)
    spherical_coefficient_m: float = field(default=.004, init=False)
    chromatic_coefficient_m: float = field(default=.002, init=False)
    residual_sigma_m: float = field(default=5e-9, init=False)
    astigmatic_plane_scale_m: float = field(default=3e-6, init=False)
    bse_response_sigma_m: float = field(default=150e-9, init=False)
    _focus_reference_m: float = field(default=1.2e-6, init=False, repr=False)
    _stig_reference_x: float = field(default=.18, init=False, repr=False)
    _stig_reference_y: float = field(default=-.12, init=False, repr=False)

    def components(self, current_A):
        current = _real(current_A, 1e-12, 1e-9, 'current_A')
        alpha = self.semiangle_rad
        wavelength = electron_wavelength_m(self.energy_eV)
        source = 2.0 / (math.pi * alpha) * math.sqrt(
            current / (self.reduced_brightness * self.energy_eV))
        diffraction = .61 * wavelength / alpha
        spherical = .5 * self.spherical_coefficient_m * alpha**3
        chromatic = self.chromatic_coefficient_m * alpha * self.energy_spread_eV / self.energy_eV
        sigma = math.sqrt(self.residual_sigma_m**2 +
                          math.fsum(d*d for d in (source, diffraction, spherical, chromatic)) /
                          DIAMETER_TO_SIGMA**2)
        return BlurComponents(wavelength, source, diffraction, spherical, chromatic, sigma)

    def covariance(self, settings, surface_height_m=0.0):
        if type(settings) is not BeamSettings:
            raise ValueError('exact BeamSettings required')
        height = _real(surface_height_m, -HEIGHT_BOUND_M, HEIGHT_BOUND_M, 'surface_height_m')
        dx = settings.stigmator_x - self._stig_reference_x
        dy = settings.stigmator_y - self._stig_reference_y
        astig = self.astigmatic_plane_scale_m * math.hypot(dx, dy)
        theta = .5 * math.atan2(dy, dx) if astig else 0.0
        defocus = settings.focus_offset_m - self._focus_reference_m + height
        base = self.components(settings.current_A).sigma_base_m**2
        scale = self.semiangle_rad**2 / 4.0
        a = base + scale * (defocus - astig)**2
        b = base + scale * (defocus + astig)**2
        c, s = math.cos(theta), math.sin(theta)
        return Covariance2D(a*c*c + b*s*s, (a-b)*c*s, a*s*s + b*c*c)

    def channel_covariance(self, settings, surface_height_m, channel):
        if type(channel) is not str or channel not in ('SE', 'BSE'):
            raise ValueError('exact SE or BSE channel required')
        primary = self.covariance(settings, surface_height_m)
        if channel == 'SE':
            return primary
        broadening = self.bse_response_sigma_m**2
        return Covariance2D(primary.xx_m2 + broadening, primary.xy_m2,
                            primary.yy_m2 + broadening)


def gaussian_quadrature(covariance, channel='SE'):
    if type(covariance) is not Covariance2D:
        raise ValueError('exact Covariance2D required')
    if type(channel) is not str or channel not in ('SE', 'BSE'):
        raise ValueError('exact SE or BSE channel required')
    low, high = covariance.principal_variances_m2()
    sigma_a, sigma_b = math.sqrt(high), math.sqrt(low)
    if sigma_a > 200e-9:
        raise ValueError('quadrature width outside B0 numerical envelope')
    theta = .5 * math.atan2(2.0 * covariance.xy_m2, covariance.xx_m2 - covariance.yy_m2)
    c, s = math.cos(theta), math.sin(theta)
    cap = 12.5e-9 if channel == 'SE' else 62.5e-9
    axes = []
    for sigma in (sigma_a, sigma_b):
        n = math.ceil(4.5 * sigma / min(sigma/3.0, cap))
        axes.append(tuple((i*4.5*sigma/n, math.exp(-.5*(i*4.5/n)**2))
                          for i in range(-n, n+1)))
    rows = tuple((c*u-s*v, s*u+c*v, wu*wv)
                 for u, wu in axes[0] for v, wv in axes[1])
    total = math.fsum(row[2] for row in rows)
    return tuple((x, y, weight/total) for x, y, weight in rows)
