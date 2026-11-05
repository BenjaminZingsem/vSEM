"""Verified scalar owner with observable,beam-blanked numerical sweep pacing."""
from .human_verified_episode import GroundedEpisode as VerifiedOwner
from .human_episode_types import EpisodeInputs, exact
from runtime.human_live_records import SweepDelivery


class GroundedEpisode(VerifiedOwner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_ended = self.last_delivered = None

    def _end_capture(self, capture, at, reason):
        generation = capture.session_generation
        identifier = capture.identity
        super()._end_capture(capture, at, reason)
        fact = next(f for f in reversed(self._facts) if f.kind == 'RASTER_END' and f.body[0] == identifier)
        self.last_ended = (identifier, fact.ordinal, generation)

    def _start(self, stop_valid):
        session = self.session
        if (session is not None and session['mode'] == 'LIVE' and session['sweep'] >= 0 and
                self.last_ended is not None and self.last_ended[2] == session['generation'] and
                self.last_delivered != self.last_ended[:2]):
            return
        super()._start(stop_valid)

    def tick(self, at_ns, inputs=EpisodeInputs(), delivery=None):
        if delivery is not None:
            exact(delivery, SweepDelivery)
            if (delivery.episode_namespace == self.episode and self.last_ended is not None and
                    delivery.causal_raster_id == self.last_ended[0] and
                    delivery.numerical_ordinal == self.last_ended[1]):
                self.last_delivered = self.last_ended[:2]
        return super().tick(at_ns, inputs)
