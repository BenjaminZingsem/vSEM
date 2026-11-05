"""Trusted OFF-ACTOR static grounded response descriptors and exact resolution.

READY validates an immutable source descriptor/domain,not a fabricated image or
a fully precomputed raster. Actual responses use the unchanged qualified B0/B1
functions in the numerical follower. This module belongs to no public transport.
"""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np

from .beam_profile import BeamProfile, BeamSettings, HEIGHT_BOUND_M
from .fine_specimen import FineSpecimen
from .grounded_response import prepare_response
from .primary_fluence import CELL_SIZES_M
from .episode_detector_counts import PROTOCOL
from .human_episode_types import (ScienceIdentity, ScalarBankHandle, BankTicket, BankReady,
    EpisodeSettings, exact, integer)

SOURCE_NAMES = ('beam_profile.py', 'fine_specimen.py', 'procedural_specimen.py',
    'primary_fluence.py', 'grounded_response.py', 'elapsed_grounded_response.py',
    'elapsed_raster.py', 'episode_detector_counts.py', 'human_episode_response_source.py', 'human_episode_types.py')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=True, allow_nan=False).encode('ascii')).hexdigest()


def source_identity():
    folder = Path(__file__).resolve().parent
    return {'python': sys.version, 'numpy': np.__version__, 'byteorder': sys.byteorder,
            'source': {name: hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in SOURCE_NAMES}}


def _settings(settings, geometry):
    # Rigid upward specimen translation changes paraxial defocus,not lens
    # readback or lateral sampling. Keep signed-zero optics exact at Z=0.
    focus = settings.focus_offset_m if geometry.stage_z_m == 0.0 else settings.focus_offset_m+geometry.stage_z_m
    return BeamSettings(settings.current_pA/10**12, focus,
                        settings.stigmator_x, settings.stigmator_y)


def _handle_digest(science, configuration, settings):
    geometry = configuration.geometry
    return _digest({'science': [science.profile_id, science.specimen_digest,
        science.grid_digest, science.vector_mode, science.solver_source_digest, science.count_model_id],
        'geometry': list(geometry._key()), 'dwell_ns': configuration.dwell_ns,
        'settings': list(settings._key()), 'kind': 'verified-static-grounded-human-xyz.v1'})


@dataclass(frozen=True)
class ResolvedSource:
    handle: ScalarBankHandle
    profile: BeamProfile
    specimen: FineSpecimen
    cell_size_m: float
    vectorized: bool

    def response(self, pixel_index):
        x, y = self.handle.geometry.pixel_center(pixel_index)
        return prepare_response(self.profile, self.specimen, _settings(self.handle.settings, self.handle.geometry),
                                x, y, cell_size_m=self.cell_size_m, vectorized=self.vectorized)


class EpisodeResponseRegistry:
    """One fixed scientific source; no operator-selected callable/assets/routes."""
    def __init__(self, *, specimen=None, cell_size_m=25e-9, vectorized=True,
                 generation=1, binding_capacity=4096):
        integer(generation, 1); integer(binding_capacity, 1)
        if specimen is None:
            specimen = FineSpecimen()
        exact(specimen, FineSpecimen)
        if type(cell_size_m) is not float or cell_size_m not in CELL_SIZES_M or type(vectorized) is not bool:
            raise ValueError('exact qualified source/grid/vector mode required')
        self.profile, self.specimen = BeamProfile(), specimen
        self.cell_size_m, self.vectorized = cell_size_m, vectorized
        self.generation, self.capacity = generation, binding_capacity
        self.pins = source_identity()
        self.science = ScienceIdentity('generic-fe-sem-human-xyz-v1',
            _digest({'specimen_id': specimen.specimen_id, 'private_seed_hex': specimen.seed.hex()}),
            _digest({'cell_size_m': cell_size_m.hex(), 'coordinate_transform': 'stage-xy-raster-y-up-v1'}),
            'VECTOR' if vectorized else 'SCALAR', _digest(self.pins), PROTOCOL)
        self._bindings = {}
        self._tickets = {}

    def _domain(self, ticket):
        geometry = ticket.configuration.geometry
        settings = _settings(ticket.settings, geometry)
        bound = self.specimen.bounds()
        if .36*math.sqrt(1+bound.slope_magnitude**2) > 4.0:
            raise ValueError('qualified specimen slope/emission envelope exceeded')
        # Bound EVERY sampled kernel over the declared surface-height envelope.
        # Covariance axes are quadratic in height; maxima occur at the endpoints.
        radii_x, radii_y = [], []
        for height in (-HEIGHT_BOUND_M, HEIGHT_BOUND_M):
            for channel in ('SE', 'BSE'):
                covariance = self.profile.channel_covariance(settings, height, channel)
                # Gaussian quadrature is a rotated rectangle of principal-axis
                # support,so use its projected rectangle,not an ellipse radius.
                low, high = covariance.principal_variances_m2()
                angle = .5*math.atan2(2*covariance.xy_m2, covariance.xx_m2-covariance.yy_m2)
                major, minor = math.sqrt(high), math.sqrt(low)
                radii_x.append(4.5*(abs(math.cos(angle))*major+abs(math.sin(angle))*minor))
                radii_y.append(4.5*(abs(math.sin(angle))*major+abs(math.cos(angle))*minor))
        rx, ry = math.nextafter(max(radii_x), math.inf), math.nextafter(max(radii_y), math.inf)
        corners = (0, geometry.width_px-1, (geometry.height_px-1)*geometry.width_px, geometry.pixel_count-1)
        for index in corners:
            x, y = geometry.pixel_center(index)
            if abs(x)+rx > .055 or abs(y)+ry > .055:
                raise ValueError('unclipped response footprint outside qualified specimen domain')

    def prepare(self, ticket):
        exact(ticket, BankTicket)
        if ticket.science != self.science or ticket.custodian_generation != self.generation:
            raise ValueError('foreign scientific source or custodian generation')
        if source_identity() != self.pins:
            raise ValueError('scientific source changed before descriptor admission')
        old = self._tickets.get(ticket.job_id)
        if old is not None:
            if old[0] != ticket:
                raise ValueError('owned job identity rebound')
            return BankReady(ticket, old[1])
        if len(self._bindings) >= self.capacity:
            raise ValueError('qualified response binding capacity exhausted')
        self._domain(ticket)
        descriptor = _handle_digest(self.science, ticket.configuration, ticket.settings)
        handle = ScalarBankHandle('source-'+str(len(self._bindings)+1), self.generation,
            descriptor, self.science.solver_source_digest, ticket.configuration.geometry, ticket.settings)
        source = ResolvedSource(handle, self.profile, self.specimen, self.cell_size_m, self.vectorized)
        self._bindings[handle.handle_id] = source
        self._tickets[ticket.job_id] = (ticket, handle)
        return BankReady(ticket, handle)

    def resolve(self, handle):
        exact(handle, ScalarBankHandle)
        source = self._bindings.get(handle.handle_id)
        if (source is None or source.handle != handle or handle.source_binding_digest != self.science.solver_source_digest
                or handle.custodian_generation != self.generation):
            raise ValueError('unregistered/rebound exact source handle')
        return source
