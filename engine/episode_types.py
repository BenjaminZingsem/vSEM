"""Closed scalar vocabulary for the new causal owner; no source/solver imports.

Representational ranges are not runtime admission or calibration evidence.
"""
from dataclasses import dataclass
import math

SAFE_INTEGER = 2**53-1
MAX_AXIS_PIXELS = 4096
MINIMUM_APPLICATION_NS = 50_000_000


def integer(value, low=0, high=SAFE_INTEGER):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('exact integer outside scalar envelope')
    return value


def real(value, low, high):
    if type(value) not in (int, float) or not low <= value <= high:
        raise ValueError('exact finite real outside scalar envelope')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('finite scalar required')
    return value


def identity(value):
    if type(value) is not str or not 1 <= len(value) <= 64:
        raise ValueError('bounded exact ASCII identity required')
    alphanumeric = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    if value[0] not in alphanumeric or any(c not in alphanumeric+'_.:-' for c in value):
        raise ValueError('closed ASCII identity required')
    return value


def digest(value):
    if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('exact lowercase SHA256 identity required')
    return value


def exact(value, cls):
    if type(value) is not cls:
        raise ValueError('exact closed scalar record required')
    return value


def choice(value, values):
    if type(value) is not str or value not in values:
        raise ValueError('closed scalar enum required')
    return value


@dataclass(frozen=True)
class ScienceIdentity:
    profile_id: str
    specimen_digest: str
    grid_digest: str
    vector_mode: str
    solver_source_digest: str
    count_model_id: str

    def __post_init__(self):
        identity(self.profile_id); identity(self.count_model_id)
        for value in (self.specimen_digest, self.grid_digest, self.solver_source_digest):
            digest(value)
        choice(self.vector_mode, ('SCALAR', 'VECTOR'))


@dataclass(frozen=True, eq=False)
class EpisodeSettings:
    current_pA: int
    focus_offset_m: float = 0.0
    stigmator_x: float = 0.0
    stigmator_y: float = 0.0

    def __post_init__(self):
        integer(self.current_pA, 1, 1000)
        for name, lower, upper in (('focus_offset_m', -25e-6, 25e-6),
                                  ('stigmator_x', -1., 1.), ('stigmator_y', -1., 1.)):
            object.__setattr__(self, name, real(getattr(self, name), lower, upper))

    def _key(self):
        return (self.current_pA, self.focus_offset_m.hex(),
                self.stigmator_x.hex(), self.stigmator_y.hex())

    def __eq__(self, other):
        return type(other) is EpisodeSettings and self._key() == other._key()

    def __hash__(self):
        return hash(self._key())


@dataclass(frozen=True, eq=False)
class EpisodeGeometry:
    width_px: int
    height_px: int
    field_width_m: float
    stage_x_m: float = 0.0
    stage_y_m: float = 0.0
    offset_x_m: float = 0.0
    offset_y_m: float = 0.0

    def __post_init__(self):
        integer(self.width_px, 1, MAX_AXIS_PIXELS)
        integer(self.height_px, 1, MAX_AXIS_PIXELS)
        for name, lower, upper in (('field_width_m', 1e-6, .005),
                ('stage_x_m', -.05, .05), ('stage_y_m', -.05, .05),
                ('offset_x_m', -.005, .005), ('offset_y_m', -.005, .005)):
            object.__setattr__(self, name, real(getattr(self, name), lower, upper))
        real(self.center_x_m, -.055, .055); real(self.center_y_m, -.055, .055)
        # The prior bank discovered out-of-domain pixel centres during preparation.
        # This new scalar envelope rejects them before any physical admission.
        for index in (0, self.width_px-1,
                      (self.height_px-1)*self.width_px, self.pixel_count-1):
            self.pixel_center(index)

    @property
    def pixel_count(self):
        return self.width_px*self.height_px

    @property
    def pixel_size_m(self):
        return self.field_width_m/self.width_px

    @property
    def center_x_m(self):
        return self.stage_x_m+self.offset_x_m

    @property
    def center_y_m(self):
        return self.stage_y_m+self.offset_y_m

    def pixel_center(self, index):
        integer(index, 0, self.pixel_count-1)
        row, column = divmod(index, self.width_px)
        x = self.center_x_m+(column+.5-self.width_px/2)*self.pixel_size_m
        y = self.center_y_m+(self.height_px/2-row-.5)*self.pixel_size_m
        return real(x, -.055, .055), real(y, -.055, .055)

    def _key(self):
        return (self.width_px, self.height_px, self.field_width_m.hex(),
                self.stage_x_m.hex(), self.stage_y_m.hex(),
                self.offset_x_m.hex(), self.offset_y_m.hex())

    def __eq__(self, other):
        return type(other) is EpisodeGeometry and self._key() == other._key()

    def __hash__(self):
        return hash(self._key())


def same_settings(a, b):
    """Numeric NO_CHANGE comparison; source bindings use the bit-exact equality."""
    exact(a, EpisodeSettings); exact(b, EpisodeSettings)
    return (a.current_pA, a.focus_offset_m, a.stigmator_x, a.stigmator_y) == (
            b.current_pA, b.focus_offset_m, b.stigmator_x, b.stigmator_y)


@dataclass(frozen=True)
class ScanRequest:
    """Operator scan scalars; stage position is bound solely by the owner."""
    width_px: int
    height_px: int
    field_width_m: float
    offset_x_m: float
    offset_y_m: float
    dwell_ns: int

    def __post_init__(self):
        integer(self.width_px, 1, MAX_AXIS_PIXELS)
        integer(self.height_px, 1, MAX_AXIS_PIXELS)
        integer(self.dwell_ns, 10, 10_000_000)
        for name, lower, upper in (('field_width_m', 1e-6, .005),
                                  ('offset_x_m', -.005, .005), ('offset_y_m', -.005, .005)):
            object.__setattr__(self, name, real(getattr(self, name), lower, upper))

    def bind(self, stage_x_m, stage_y_m):
        return ScanConfiguration(EpisodeGeometry(self.width_px, self.height_px,
            self.field_width_m, stage_x_m, stage_y_m, self.offset_x_m, self.offset_y_m), self.dwell_ns)


@dataclass(frozen=True)
class ScanConfiguration:
    geometry: EpisodeGeometry
    dwell_ns: int

    def __post_init__(self):
        exact(self.geometry, EpisodeGeometry)
        integer(self.dwell_ns, 10, 10_000_000)


@dataclass(frozen=True)
class ScalarBankHandle:
    handle_id: str
    custodian_generation: int
    descriptor_digest: str
    source_binding_digest: str
    geometry: EpisodeGeometry
    settings: EpisodeSettings

    def __post_init__(self):
        identity(self.handle_id); integer(self.custodian_generation, 1)
        digest(self.descriptor_digest); digest(self.source_binding_digest)
        exact(self.geometry, EpisodeGeometry); exact(self.settings, EpisodeSettings)


@dataclass(frozen=True)
class AuthorityRef:
    holder_id: str
    epoch: int

    def __post_init__(self):
        identity(self.holder_id); integer(self.epoch, 1)


@dataclass(frozen=True)
class LeaseState:
    authority: AuthorityRef
    expires_ns: int

    def __post_init__(self):
        exact(self.authority, AuthorityRef); integer(self.expires_ns, 1)


@dataclass(frozen=True)
class GrantAuthority:
    operation_id: str
    holder_id: str
    expires_ns: int

    def __post_init__(self):
        identity(self.operation_id); identity(self.holder_id); integer(self.expires_ns, 1)


@dataclass(frozen=True)
class RenewAuthority:
    operation_id: str
    authority: AuthorityRef
    expires_ns: int

    def __post_init__(self):
        identity(self.operation_id); exact(self.authority, AuthorityRef); integer(self.expires_ns, 1)


@dataclass(frozen=True)
class RevokeAuthority:
    operation_id: str
    authority: AuthorityRef

    def __post_init__(self):
        identity(self.operation_id); exact(self.authority, AuthorityRef)


@dataclass(frozen=True)
class StartCapture:
    operation_id: str
    authority: AuthorityRef
    mode: str
    request: ScanRequest
    expected_stop_generation: int

    def __post_init__(self):
        identity(self.operation_id); exact(self.authority, AuthorityRef)
        choice(self.mode, ('SINGLE', 'LIVE')); exact(self.request, ScanRequest)
        integer(self.expected_stop_generation)


@dataclass(frozen=True)
class ConfigureLive:
    operation_id: str
    authority: AuthorityRef
    request: ScanRequest
    expected_stop_generation: int

    def __post_init__(self):
        identity(self.operation_id); exact(self.authority, AuthorityRef)
        exact(self.request, ScanRequest); integer(self.expected_stop_generation)


@dataclass(frozen=True)
class SetOptics:
    operation_id: str
    authority: AuthorityRef
    settings: EpisodeSettings

    def __post_init__(self):
        identity(self.operation_id); exact(self.authority, AuthorityRef)
        exact(self.settings, EpisodeSettings)


@dataclass(frozen=True)
class MoveStage:
    operation_id: str
    authority: AuthorityRef
    x_m: float
    y_m: float
    expected_stop_generation: int

    def __post_init__(self):
        identity(self.operation_id); exact(self.authority, AuthorityRef)
        integer(self.expected_stop_generation)
        object.__setattr__(self, 'x_m', real(self.x_m, -.025, .025))
        object.__setattr__(self, 'y_m', real(self.y_m, -.025, .025))


@dataclass(frozen=True)
class SafetyStop:
    operation_id: str
    authority: AuthorityRef

    def __post_init__(self):
        identity(self.operation_id); exact(self.authority, AuthorityRef)


@dataclass(frozen=True)
class FreezeLive:
    operation_id: str
    authority: AuthorityRef
    live_view_id: str
    expected_stop_generation: int

    def __post_init__(self):
        identity(self.operation_id); exact(self.authority, AuthorityRef)
        identity(self.live_view_id); integer(self.expected_stop_generation)


@dataclass(frozen=True)
class BankTicket:
    job_id: str
    request_id: str
    purpose: str
    authority: AuthorityRef
    session_generation: int
    settings_generation: int
    geometry_generation: int
    applied_generation: int
    custodian_generation: int
    science: ScienceIdentity
    configuration: ScanConfiguration
    settings: EpisodeSettings
    not_before_ns: int

    def __post_init__(self):
        identity(self.job_id); identity(self.request_id)
        choice(self.purpose, ('SETTINGS', 'INITIAL_CAPTURE'))
        exact(self.authority, AuthorityRef)
        for value in (self.session_generation, self.settings_generation,
                      self.geometry_generation, self.applied_generation):
            integer(value)
        integer(self.custodian_generation, 1); integer(self.not_before_ns)
        exact(self.science, ScienceIdentity); exact(self.configuration, ScanConfiguration)
        exact(self.settings, EpisodeSettings)


@dataclass(frozen=True)
class BankReady:
    ticket: BankTicket
    handle: ScalarBankHandle

    def __post_init__(self):
        exact(self.ticket, BankTicket); exact(self.handle, ScalarBankHandle)
        if (self.handle.geometry != self.ticket.configuration.geometry or
                self.handle.settings != self.ticket.settings or
                self.handle.custodian_generation != self.ticket.custodian_generation):
            raise ValueError('ready handle differs from owned scalar ticket')


@dataclass(frozen=True)
class BankFailed:
    ticket: BankTicket
    reason: str = 'BANK_FAILED'

    def __post_init__(self):
        exact(self.ticket, BankTicket); choice(self.reason, ('BANK_FAILED',))


@dataclass(frozen=True)
class VerifiedAcknowledgement:
    episode_namespace: str
    last_ordinal: int

    def __post_init__(self):
        identity(self.episode_namespace); integer(self.last_ordinal)


@dataclass(frozen=True)
class EpisodeFault:
    episode_namespace: str
    reason: str

    def __post_init__(self):
        identity(self.episode_namespace)
        choice(self.reason, ('NUMERIC_FAILURE', 'CAUSAL_FAILURE', 'PROCESS_FAILURE', 'SPOOL_CAPACITY', 'TIME_RANGE'))


@dataclass(frozen=True)
class EpisodeInputs:
    authority: object = None
    stop: object = None
    normal: object = None
    bank_result: object = None
    verified_ack: object = None
    fault: object = None

    def __post_init__(self):
        permitted = ((self.authority, (GrantAuthority, RenewAuthority, RevokeAuthority)),
                     (self.stop, (SafetyStop,)),
                     (self.normal, (StartCapture, ConfigureLive, SetOptics, MoveStage, FreezeLive)),
                     (self.bank_result, (BankReady, BankFailed)),
                     (self.verified_ack, (VerifiedAcknowledgement,)),
                     (self.fault, (EpisodeFault,)))
        for value, types in permitted:
            if value is not None and type(value) not in types:
                raise ValueError('exact closed optional scalar input required')
