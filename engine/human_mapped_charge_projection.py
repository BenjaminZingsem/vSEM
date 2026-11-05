"""Canonical charge-supplied immutable B1a projection; no clock/ledger/noise."""
from dataclasses import dataclass, field
from itertools import chain
import math
from .beam_profile import ELEMENTARY_CHARGE_C
from .human_mapped_response_source import MappedResponse
from .primary_fluence import NumericalConvergenceError
from .elapsed_raster import _integer, _objects, incident_charge_C, SOLVER_ID


def _charge_inputs(response, current_pA, incident_pA_ns):
    if type(response) is not MappedResponse:
        raise ValueError('exact immutable grounded response required')
    _integer(current_pA, 1, 1000, 'applied pA')
    _integer(incident_pA_ns, name='incident pA ns')
    if response.settings.current_A != current_pA/10**12:
        raise ValueError('response current differs from canonical applied pA')
    if incident_pA_ns % current_pA:
        raise ValueError('same-current charge must represent integer exposed ns')


def _finite(value, signed=False):
    if type(value) is not float or not math.isfinite(value) or (not signed and value < 0):
        raise ValueError('finite exact projected float required')


@dataclass(frozen=True)
class ElapsedCellCharge:
    index_x: int
    index_y: int
    charge_C: float

    def __post_init__(self):
        # Signed lattice indices inherit B1a's finite coordinate/grid envelope.
        if type(self.index_x) is not int or type(self.index_y) is not int:
            raise ValueError('exact cell indices required')
        _finite(self.charge_C)


@dataclass(frozen=True)
class ElapsedGroundedExposure:
    response: MappedResponse
    current_pA: int
    incident_pA_ns: int
    exposure_ns: int
    incident_charge_C: float
    incident_electrons: float
    se_mean: float
    bse_mean: float
    se_emitted_charge_C: float
    bse_emitted_charge_C: float
    ground_charge_C: float
    cell_charges: tuple
    tail_charge_C: float
    protocol: str = field(default='vsem.human-mapped-charge-exposure.v1', init=False)
    solver_id: str = field(default=SOLVER_ID, init=False)

    def __post_init__(self):
        _charge_inputs(self.response, self.current_pA, self.incident_pA_ns)
        _integer(self.exposure_ns, name='exposure ns')
        if self.exposure_ns != self.incident_pA_ns//self.current_pA:
            raise ValueError('exposed ns differs from canonical charge')
        for name in ('incident_charge_C', 'incident_electrons', 'se_mean', 'bse_mean',
                     'se_emitted_charge_C', 'bse_emitted_charge_C', 'tail_charge_C'):
            _finite(getattr(self, name))
        _finite(self.ground_charge_C, signed=True)
        _objects(self.cell_charges, ElapsedCellCharge, 'cell charge')
        source = self.response
        q = incident_charge_C(self.incident_pA_ns)
        electrons = q/ELEMENTARY_CHARGE_C
        se, bse = q*source.se_emitted_per_incident, q*source.bse_emitted_per_incident
        expected = (q, electrons, electrons*source.se_collected_per_incident,
            electrons*source.bse_collected_per_incident, se, bse, math.fsum((q, -se, -bse)),
            q*source.fluence.tail_probability)
        actual = (self.incident_charge_C, self.incident_electrons, self.se_mean, self.bse_mean,
            self.se_emitted_charge_C, self.bse_emitted_charge_C, self.ground_charge_C, self.tail_charge_C)
        if actual != expected or len(self.cell_charges) != len(source.fluence.cells):
            raise ValueError('projected exposure differs from canonical Q/response')
        for cell, original in zip(self.cell_charges, source.fluence.cells):
            if (cell.index_x, cell.index_y, cell.charge_C) != (
                    original.index_x, original.index_y, q*original.probability):
                raise ValueError('cell charge differs from original primary fluence')
        deposited = math.fsum(chain((c.charge_C for c in self.cell_charges), (self.tail_charge_C,)))
        imbalance = math.fsum((-q, se, bse, self.ground_charge_C))
        if q == 0:
            if any(v != 0.0 for v in actual) or any(c.charge_C != 0.0 for c in self.cell_charges):
                raise NumericalConvergenceError('exact zero exposure required')
        elif abs(deposited-q) > 8*math.ulp(q) or abs(imbalance) > 8*math.ulp(q):
            raise NumericalConvergenceError('canonical Q charge closure failed')


def exposure_for_charge(response, *, current_pA, incident_pA_ns):
    _charge_inputs(response, current_pA, incident_pA_ns)
    q = incident_charge_C(incident_pA_ns)
    electrons = q/ELEMENTARY_CHARGE_C
    se, bse = q*response.se_emitted_per_incident, q*response.bse_emitted_per_incident
    return ElapsedGroundedExposure(response, current_pA, incident_pA_ns,
        incident_pA_ns//current_pA, q, electrons,
        electrons*response.se_collected_per_incident, electrons*response.bse_collected_per_incident,
        se, bse, math.fsum((q, -se, -bse)),
        tuple(ElapsedCellCharge(c.index_x, c.index_y, q*c.probability) for c in response.fluence.cells),
        q*response.fluence.tail_probability)
