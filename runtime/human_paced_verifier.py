"""Independent sweep pacing certificates,attested by actual numerical cuts."""
from engine import human_episode_types as t
from .human_causal_verifier import HumanCausalVerifier
from .human_realtime_records import TickBegin
from .human_live_records import LiveTickBegin, SweepDelivery


class PacedCausalVerifier(HumanCausalVerifier):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_ended = self.last_delivered = None
        self.attested = set()

    def register_delivery(self, delivery):
        t.exact(delivery, SweepDelivery)
        if delivery.episode_namespace != self.namespace: raise ValueError('Foreign numerical delivery attestation')
        self.attested.add((delivery.causal_raster_id, delivery.numerical_ordinal))

    def _end_capture(self, event, reason):
        identifier, generation = self.capture['id'], self.session['generation']
        super()._end_capture(event, reason)
        fact = next(f for f in reversed(self.expected) if f.kind == 'RASTER_END' and f.body[0] == identifier)
        self.last_ended = (identifier, fact.ordinal, generation)

    def _start(self, stop_valid):
        session = self.session
        if (session is not None and session['mode'] == 'LIVE' and session['sweep'] >= 0 and
                self.last_ended is not None and self.last_ended[2] == session['generation'] and
                self.last_delivered != self.last_ended[:2]): return
        super()._start(stop_valid)

    def verify(self, begin, facts, end):
        if self.poison is not None: raise ValueError('Paced verifier is quarantined')
        try:
            t.exact(begin, LiveTickBegin)
            delivery = begin.delivery
            if (delivery is not None and delivery.episode_namespace == self.namespace and self.last_ended is not None and
                    delivery.causal_raster_id == self.last_ended[0] and delivery.numerical_ordinal == self.last_ended[1]):
                if self.last_ended[:2] not in self.attested: raise ValueError('No actual numerical delivery attestation')
                self.last_delivered = self.last_ended[:2]
            return super().verify(TickBegin(begin.tick_id, begin.at_ns, begin.inputs), facts, end)
        except Exception as exc:
            self.poison = str(exc); raise
