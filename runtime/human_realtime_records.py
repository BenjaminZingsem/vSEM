"""Private runtime witnesses. These are never public observation envelopes."""
from dataclasses import dataclass
from engine import human_episode_types as t
from engine.human_episode_facts import EpisodeState


@dataclass(frozen=True)
class TickBegin:
    tick_id: int
    at_ns: int
    inputs: t.EpisodeInputs

    def __post_init__(self):
        t.integer(self.tick_id, 1); t.integer(self.at_ns)
        t.exact(self.inputs, t.EpisodeInputs)


@dataclass(frozen=True)
class TickEnd:
    tick_id: int
    state: EpisodeState
    bank_dispatch: object
    started: tuple
    ended: tuple

    def __post_init__(self):
        t.integer(self.tick_id, 1); t.exact(self.state, EpisodeState)
        if self.bank_dispatch is not None: t.exact(self.bank_dispatch, t.BankTicket)
        for value in (self.started, self.ended):
            t.exact(value, tuple)
            if len(value) > 1: raise ValueError('At most one raster start/end per owner service')
            for item in value: t.identity(item)


@dataclass(frozen=True)
class NumericalCut:
    last_ordinal: int
    physical_sequence: int
    episode_incident_pA_ns: int
    causal_raster_id: object = None
    outcome: object = None
    width_px: int = 0
    height_px: int = 0
    capture_incident_pA_ns: int = 0
    se_raw_sha256: object = None
    bse_raw_sha256: object = None

    def __post_init__(self):
        t.integer(self.last_ordinal); t.integer(self.physical_sequence)
        t.integer(self.episode_incident_pA_ns, high=2**64-1)
        t.integer(self.capture_incident_pA_ns, high=2**64-1)
        for value in (self.causal_raster_id, self.outcome):
            if value is not None: t.identity(value)
        for value in (self.se_raw_sha256, self.bse_raw_sha256):
            if value is not None: t.digest(value)
        t.integer(self.width_px, 0, 4096); t.integer(self.height_px, 0, 4096)
        if self.causal_raster_id is None:
            if (self.outcome is not None or self.width_px or self.height_px or
                    self.capture_incident_pA_ns or self.se_raw_sha256 or self.bse_raw_sha256):
                raise ValueError('Empty numerical cut cannot contain a capture')
        elif not self.width_px or not self.height_px or self.outcome is None:
            raise ValueError('Capture cut requires native dimensions and outcome')
