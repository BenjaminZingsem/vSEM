"""Adversarial parent forwarding fixtures,not solver/process qualification."""
from collections import deque
from dataclasses import replace
import unittest

from acceptance.test_human_causal_verifier import Probe, SCIENCE, CAP, INITIAL
from engine import human_episode_types as t
from runtime.human_causal_verifier import HumanCausalVerifier
from runtime.human_checked_kernel import CheckedRealtimeKernel
from runtime.human_realtime_kernel import RetainedCells
from runtime.human_realtime_codec import encode_cell


def parent_fixture():
    value = CheckedRealtimeKernel.__new__(CheckedRealtimeKernel)
    value.namespace = 'fixture'; value.retained = RetainedCells(1000, 1000)
    value.records, value.facts, value.dispatches = [], [], []
    value._numeric_pending, value._jobs_pending = deque(), deque()
    value._active_tick = value._candidate_begin = value.state = value.causal_cut = value.causal_error = None
    value._last_tick = value._last_ordinal = value._last_physical = 0
    value._candidate_facts = []
    value.verifier = HumanCausalVerifier(SCIENCE, INITIAL, episode_namespace='fixture', capacity=CAP)
    value.faults = []
    value.fault = value.faults.append  # parent signal spy only;no numerical mock
    return value


class CheckedForwardingTests(unittest.TestCase):
    def send(self, parent, value):
        cell = encode_cell(value, bytes(16), len(parent.records)+1)
        parent._retain(value, cell)
        self.assertEqual(parent.retained.cells[-1], cell)

    def test_partial_tick_keeps_all_facts_and_dispatch_out_of_numeric_lane(self):
        p = Probe(ack=False); parent = parent_fixture()
        for begin, facts, end in p.services:
            for value in (begin, *facts, end): self.send(parent, value)
        parent._numeric_pending.clear()
        prior = parent.causal_cut
        p.tick(1, t.EpisodeInputs(normal=t.StartCapture('scan', p.authority, 'SINGLE', t.ScanRequest(2,2,1e-6,0.,0.,1000),0)))
        begin, facts, end = p.services[-1]
        for value in (begin, *facts): self.send(parent, value)
        self.assertEqual(list(parent._numeric_pending), [])
        self.assertEqual(list(parent._jobs_pending), [])
        self.assertIs(parent.causal_cut, prior)
        self.send(parent, end)
        self.assertEqual(list(parent._numeric_pending), list(facts))
        self.assertEqual(list(parent._jobs_pending), [end.bank_dispatch])
        self.assertEqual(parent.causal_cut.last_ordinal, end.state.last_ordinal)

    def test_invalid_complete_tick_preserves_prior_cut_and_retains_quarantined_bytes(self):
        p = Probe(ack=False); parent = parent_fixture()
        for begin, facts, end in p.services:
            for value in (begin, *facts, end): self.send(parent, value)
        parent._numeric_pending.clear(); prior = parent.causal_cut
        p.tick(1, t.EpisodeInputs(normal=t.StartCapture('scan',p.authority,'SINGLE',t.ScanRequest(2,2,1e-6,0.,0.,1000),0)))
        begin, facts, end = p.services[-1]
        for value in (begin, *facts): self.send(parent, value)
        forged = replace(end, state=replace(end.state, beam_blank=False))
        self.send(parent, forged)
        self.assertIs(parent.causal_cut, prior)
        self.assertEqual(parent.faults, ['CAUSAL_FAILURE'])
        self.assertIsNotNone(parent.causal_error)
        self.assertEqual(list(parent._numeric_pending), [])
        self.assertEqual(list(parent._jobs_pending), [])
        self.assertEqual(parent.retained.cells[-1], encode_cell(forged, bytes(16), len(parent.records)))


if __name__ == '__main__': unittest.main()
