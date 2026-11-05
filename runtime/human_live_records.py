"""Private v5 numerical-delivery evidence;no public observation payload."""
from dataclasses import dataclass
from engine import human_episode_types as t


@dataclass(frozen=True)
class SweepDelivery:
    episode_namespace: str
    causal_raster_id: str
    numerical_ordinal: int

    def __post_init__(self):
        t.identity(self.episode_namespace); t.identity(self.causal_raster_id)
        t.integer(self.numerical_ordinal, 1)


@dataclass(frozen=True)
class LiveTickBegin:
    tick_id: int
    at_ns: int
    inputs: t.EpisodeInputs
    delivery: object = None

    def __post_init__(self):
        t.integer(self.tick_id, 1); t.integer(self.at_ns); t.exact(self.inputs, t.EpisodeInputs)
        if self.delivery is not None: t.exact(self.delivery, SweepDelivery)


@dataclass(frozen=True)
class NativeImageReady:
    image_id: str
    causal_raster_id: str
    numerical_ordinal: int
    physical_sequence: int
    metadata_sha256: str

    def __post_init__(self):
        t.identity(self.image_id); t.identity(self.causal_raster_id)
        t.integer(self.numerical_ordinal, 1); t.integer(self.physical_sequence, 1)
        t.digest(self.metadata_sha256)
