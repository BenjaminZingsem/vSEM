"""Closed private scalar trace records; no solver or acquired count payload."""
from dataclasses import dataclass
import math
from .human_episode_types import (SAFE_INTEGER, integer, exact, identity, choice,
    EpisodeSettings, ScanConfiguration, ScalarBankHandle, LeaseState, MAX_STAGE_Z_M)

PHYSICAL_KINDS = ('RASTER_START', 'PREFIX', 'HOLD_START', 'HOLD_END',
    'SETTINGS_APPLIED', 'RASTER_END', 'MOTION_START', 'MOTION_ADVANCE', 'MOTION_END',
    'MOTION_XYZ_START', 'MOTION_XYZ_ADVANCE', 'MOTION_XYZ_END')
CONTROL_KINDS = ('LEASE', 'DISPOSITION', 'TARGET_RETIRED', 'SESSION_ENDED', 'GEOMETRY', 'INTERLOCK')

# Body shapes are fixed ordered scalars/closed records. "optional" is never a
# dictionary,callable,graph or arbitrary iterable. Detailed semantic validation
# belongs to the causal verifier,not to the numerical response process.
SHAPES = {
    'RASTER_START': (str, int, int, str, str, ('optional', str), ScanConfiguration, ScalarBankHandle, str),
    'PREFIX': (str, int, int, int, int, bool, ScalarBankHandle, str, int, int),
    'HOLD_START': (str, int, int, str),
    'HOLD_END': (str, int, int, int, str),
    'SETTINGS_APPLIED': (str, EpisodeSettings, EpisodeSettings, int, ScalarBankHandle,
                         ('optional', str), ('optional', int)),
    'RASTER_END': (str, int, int, int, str),
    'MOTION_START': (str, float, float, float, float, int, int),
    'MOTION_ADVANCE': (str, float, float, float, float, str),
    'MOTION_END': (str, float, float, str),
    'MOTION_XYZ_START': (str, float, float, float, float, float, float, int, int),
    'MOTION_XYZ_ADVANCE': (str, float, float, float, float, float, float, str),
    'MOTION_XYZ_END': (str, float, float, float, str),
    'LEASE': (('optional', LeaseState), str),
    'DISPOSITION': (str, str, str, str),
    'TARGET_RETIRED': (str, str),
    'SESSION_ENDED': (str, str, ('optional', str)),
    'GEOMETRY': (str, int, ScanConfiguration),
    'INTERLOCK': (str,),
}


@dataclass(frozen=True)
class EpisodeFact:
    ordinal: int
    predecessor: int
    issued_at_ns: int
    event_at_ns: int
    episode_namespace: str
    lane: str
    emergency: bool
    physical_sequence: object
    physical_predecessor: object
    kind: str
    body: tuple

    def __post_init__(self):
        integer(self.ordinal, 1); integer(self.predecessor)
        if self.predecessor != self.ordinal-1:
            raise ValueError('contiguous merged ordinal required')
        integer(self.issued_at_ns); integer(self.event_at_ns)
        if self.event_at_ns > self.issued_at_ns:
            raise ValueError('no future private physical fact')
        identity(self.episode_namespace); choice(self.lane, ('R', 'T', 'A', 'C'))
        if type(self.emergency) is not bool:
            raise ValueError('exact emergency flag required')
        choice(self.kind, PHYSICAL_KINDS+CONTROL_KINDS)
        if self.kind in PHYSICAL_KINDS:
            integer(self.physical_sequence, 1); integer(self.physical_predecessor)
            if self.physical_predecessor != self.physical_sequence-1 or self.lane == 'C':
                raise ValueError('contiguous physical predecessor/lane required')
        elif self.physical_sequence is not None or self.physical_predecessor is not None or self.lane != 'C':
            raise ValueError('control fact cannot impersonate an exposure sequence')
        shape = SHAPES[self.kind]
        if type(self.body) is not tuple or len(self.body) != len(shape):
            raise ValueError('exact closed scalar fact body required')
        for value, expected in zip(self.body, shape):
            optional = type(expected) is tuple
            if optional and value is None:
                continue
            cls = expected[1] if optional else expected
            exact(value, cls)
            if cls is int:
                integer(value, high=2**64-1)
            elif cls is str:
                identity(value)
            elif cls is float and not math.isfinite(value):
                raise ValueError('finite scalar fact real required')


@dataclass(frozen=True)
class EpisodeState:
    now_ns: int
    revision: int
    phase: str
    beam_blank: bool
    settings: EpisodeSettings
    requested_settings: object
    lease: object
    stop_generation: int
    session_generation: int
    settings_generation: int
    geometry_generation: int
    applied_generation: int
    current_configuration: object
    requested_configuration: object
    causal_raster_id: object
    live_view_id: object
    sweep_index: object
    stage_x_m: float
    stage_y_m: float
    last_ordinal: int
    physical_sequence: int
    verified_ordinal: int
    capture_incident_pA_ns: int
    episode_incident_pA_ns: int
    interlock_reason: object
    stage_z_m: float = 0.0

    def __post_init__(self):
        integer(self.now_ns); integer(self.revision)
        choice(self.phase, ('STOPPED', 'MOVING', 'CAPTURING', 'PREPARING', 'BETWEEN_SWEEPS', 'INTERLOCKED'))
        exact(self.beam_blank, bool); exact(self.settings, EpisodeSettings)
        for value, cls in ((self.requested_settings, EpisodeSettings), (self.lease, LeaseState),
                           (self.current_configuration, ScanConfiguration), (self.requested_configuration, ScanConfiguration)):
            if value is not None:
                exact(value, cls)
        for value in (self.stop_generation, self.session_generation, self.settings_generation,
                      self.geometry_generation, self.applied_generation, self.last_ordinal,
                      self.physical_sequence, self.verified_ordinal):
            integer(value)
        for value in (self.capture_incident_pA_ns, self.episode_incident_pA_ns):
            integer(value, high=2**64-1)
        for value in (self.causal_raster_id, self.live_view_id, self.interlock_reason):
            if value is not None:
                identity(value)
        if self.sweep_index is not None:
            integer(self.sweep_index)
        for value in (self.stage_x_m, self.stage_y_m):
            if type(value) is not float or not math.isfinite(value) or not -.025 <= value <= .025:
                raise ValueError('exact bounded stage state required')
        if type(self.stage_z_m) is not float or not math.isfinite(self.stage_z_m) or abs(self.stage_z_m) > MAX_STAGE_Z_M:
            raise ValueError('exact bounded Z stage state required')


@dataclass(frozen=True)
class EpisodeTickResult:
    state: EpisodeState
    facts: tuple
    bank_dispatch: object
    started_raster_ids: tuple
    ended_raster_ids: tuple

    def __post_init__(self):
        exact(self.state, EpisodeState)
        if type(self.facts) is not tuple or any(type(fact) is not EpisodeFact for fact in self.facts):
            raise ValueError('immutable exact emitted fact tuple required')
        for values in (self.started_raster_ids, self.ended_raster_ids):
            if type(values) is not tuple:
                raise ValueError('immutable identity tuple required')
            for value in values:
                identity(value)
