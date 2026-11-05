"""Scalar scheduling fixtures only; no numerical/runtime qualification claimed.

Opaque scalar READY fixtures exercise scheduling,not a mocked solver. Genuine
bank/count integration and real-process witnesses remain separate mandatory gates.
"""
import ast
import math
from pathlib import Path
import unittest
from engine.grounded_episode import GroundedEpisode, active_prefix
from engine.episode_credits import EpisodeCapacity
from engine.episode_types import (ScienceIdentity, EpisodeSettings, EpisodeInputs,
    GrantAuthority, RevokeAuthority, AuthorityRef, StartCapture, ScanRequest,
    ScalarBankHandle, BankReady, SetOptics, SafetyStop, ConfigureLive, MoveStage,
    FreezeLive, EpisodeFault, VerifiedAcknowledgement, SAFE_INTEGER)


class ScalarOwnerTests(unittest.TestCase):
    def owner(self, expiry=10**12, capacity=None):
        self.science = ScienceIdentity('generic', 'a'*64, 'b'*64, 'VECTOR', 'c'*64, 'count')
        self.engine = GroundedEpisode(self.science, EpisodeSettings(10), episode_namespace='episode1',
            capacity=capacity or EpisodeCapacity(16384, 1024, 1024, 16384, 4096, 4096))
        result = self.engine.tick(0, EpisodeInputs(authority=GrantAuthority('grant', 'human', expiry)))
        self.auth = result.state.lease.authority
        return result

    def ready(self, ticket):
        handle = ScalarBankHandle('handle-'+ticket.job_id, ticket.custodian_generation,
            'd'*64, self.science.solver_source_digest, ticket.configuration.geometry, ticket.settings)
        return BankReady(ticket, handle)

    def start(self, *, mode='LIVE', request=None, op='start', at=0, generation=0):
        request = request or ScanRequest(64, 32, 2e-6, 0., 0., 1_000_000)
        result = self.engine.tick(at, EpisodeInputs(normal=StartCapture(op, self.auth, mode, request, generation)))
        ticket = result.bank_dispatch
        if ticket is not None:
            self.engine.tick(at+1, EpisodeInputs(bank_result=self.ready(ticket)))
        return self.engine.tick(at+50_000_000)

    def test_no_source_solver_numpy_or_dynamic_import_on_physical_owner(self):
        source = (Path(__file__).resolve().parents[1]/'engine/grounded_episode.py').read_bytes()
        tree = ast.parse(source)
        forbidden = {'numpy', 'response_bank', 'grounded_response', 'specimen', 'hashlib', 'pickle', 'concurrent', 'subprocess'}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertFalse({a.name.split('.')[0] for a in node.names}&forbidden)
            elif isinstance(node, ast.ImportFrom):
                self.assertFalse(set((node.module or '').split('.'))&forbidden)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, ('__import__', 'eval', 'exec', 'open'))

    def test_initial_cached_readiness_still_waits_minimum_and_no_early_dose(self):
        self.owner()
        result = self.engine.tick(0, EpisodeInputs(normal=StartCapture('start', self.auth, 'SINGLE',
            ScanRequest(16, 16, 2e-6, 0., 0., 1000), 0)))
        self.engine.tick(1, EpisodeInputs(bank_result=self.ready(result.bank_dispatch)))
        state = self.engine.tick(49_999_999).state
        self.assertEqual((state.phase, state.episode_incident_pA_ns), ('PREPARING', 0))
        result = self.engine.tick(50_000_000)
        self.assertEqual(len(result.started_raster_ids), 1)
        self.assertEqual(result.state.episode_incident_pA_ns, 0)
        self.assertEqual(self.engine.tick(69_999_999).state.episode_incident_pA_ns, 0)
        self.assertEqual(self.engine.tick(70_000_100).state.episode_incident_pA_ns, 1000)

    def test_same_tick_stop_and_ready_prevents_initial_start(self):
        self.owner()
        result = self.engine.tick(0, EpisodeInputs(normal=StartCapture('start', self.auth, 'LIVE',
            ScanRequest(16, 16, 2e-6, 0., 0., 1000), 0)))
        result = self.engine.tick(50_000_000, EpisodeInputs(stop=SafetyStop('stop', self.auth),
            bank_result=self.ready(result.bank_dispatch)))
        self.assertEqual(result.started_raster_ids, ())
        self.assertEqual((result.state.phase, result.state.stop_generation, result.state.episode_incident_pA_ns),
                         ('STOPPED', 1, 0))

    def test_stop_fences_buffered_start_and_requires_new_generation(self):
        self.owner(); self.start()
        result = self.engine.tick(70_500_000, EpisodeInputs(stop=SafetyStop('stop', self.auth)))
        total = result.state.episode_incident_pA_ns
        stale = self.engine.tick(71_000_000, EpisodeInputs(normal=StartCapture('stale', self.auth, 'LIVE',
            ScanRequest(64, 32, 2e-6, 0., 0., 1_000_000), 0)))
        self.assertEqual(stale.state.phase, 'STOPPED')
        self.assertEqual(stale.state.episode_incident_pA_ns, total)
        self.assertTrue(any(f.kind == 'DISPOSITION' and f.body[2] == 'STOPPED_BEFORE_ADMISSION' for f in stale.facts))
        fresh = self.start(op='fresh', at=72_000_000, generation=1)
        self.assertEqual(fresh.state.phase, 'CAPTURING')

    def test_duplicate_stop_does_not_cancel_a_later_valid_session(self):
        self.owner(); self.start()
        self.engine.tick(71_000_000, EpisodeInputs(stop=SafetyStop('stop', self.auth)))
        self.start(op='fresh', at=72_000_000, generation=1)
        result = self.engine.tick(123_000_000, EpisodeInputs(stop=SafetyStop('stop', self.auth)))
        self.assertEqual((result.state.phase, result.state.stop_generation), ('CAPTURING', 1))

    def test_unauthorized_stop_has_no_control_effect_and_physics_continues(self):
        self.owner(); self.start()
        result = self.engine.tick(71_000_000, EpisodeInputs(stop=SafetyStop('other-stop', AuthorityRef('other', 1))))
        self.assertEqual(result.state.phase, 'CAPTURING')
        self.assertEqual(result.state.stop_generation, 0)
        self.assertEqual(result.state.episode_incident_pA_ns, 10_000_000)

    def test_unready_optics_due_makes_real_hold_and_conserves_split_current(self):
        self.owner(); self.start()
        target = self.engine.tick(70_500_000, EpisodeInputs(normal=SetOptics('focus', self.auth,
            EpisodeSettings(20, 4.2e-6, .18, -.12))))
        held = self.engine.tick(121_000_000)
        self.assertTrue(held.state.beam_blank)
        self.assertEqual(held.state.episode_incident_pA_ns, 505_000_000)
        self.assertTrue(any(f.kind == 'HOLD_START' and f.event_at_ns == 120_500_000 for f in held.facts))
        applied = self.engine.tick(121_000_000, EpisodeInputs(bank_result=self.ready(target.bank_dispatch)))
        self.assertEqual(applied.state.settings.current_pA, 20)
        self.assertTrue(any(f.kind == 'HOLD_END' and f.body[2]-f.body[1] == 500_000 for f in applied.facts))
        stopped = self.engine.tick(122_000_000, EpisodeInputs(stop=SafetyStop('stop', self.auth)))
        self.assertEqual(stopped.state.episode_incident_pA_ns, 525_000_000)

    def test_equal_applied_target_cancels_hold_without_relabelling_signed_zero(self):
        self.owner(); self.start()
        self.engine.tick(70_500_000, EpisodeInputs(normal=SetOptics('focus', self.auth, EpisodeSettings(10, 4e-6))))
        self.engine.tick(121_000_000)
        result = self.engine.tick(122_000_000, EpisodeInputs(normal=SetOptics('cancel', self.auth, EpisodeSettings(10, -0., -0., -0.))))
        self.assertIsNone(result.state.requested_settings)
        self.assertEqual(result.state.settings.focus_offset_m.hex(), 0.0.hex())
        self.assertFalse(any(f.kind == 'SETTINGS_APPLIED' for f in result.facts))
        self.assertTrue(any(f.kind == 'HOLD_END' for f in result.facts))
        self.assertGreater(self.engine.tick(123_000_000).state.episode_incident_pA_ns, result.state.episode_incident_pA_ns)

    def test_stop_wins_apply_but_valid_pending_target_can_apply_later_blanked(self):
        self.owner(); self.start()
        target = self.engine.tick(70_500_000, EpisodeInputs(normal=SetOptics('focus', self.auth, EpisodeSettings(10, 4e-6))))
        stopped = self.engine.tick(121_000_000, EpisodeInputs(stop=SafetyStop('stop', self.auth),
            bank_result=self.ready(target.bank_dispatch)))
        self.assertFalse(any(f.kind == 'SETTINGS_APPLIED' for f in stopped.facts))
        self.assertEqual(stopped.state.settings.focus_offset_m, 0.)
        total = stopped.state.episode_incident_pA_ns
        applied = self.engine.tick(122_000_000)
        fact = next(f for f in applied.facts if f.kind == 'SETTINGS_APPLIED')
        self.assertIsNone(fact.body[5]); self.assertIsNone(fact.body[6])
        self.assertEqual(applied.state.episode_incident_pA_ns, total)

    def test_known_expiry_cuts_before_late_tick_and_fences_old_work(self):
        self.owner(expiry=90_000_000); self.start()
        result = self.engine.tick(300_000_000)
        ended = next(f for f in result.facts if f.kind == 'RASTER_END')
        self.assertEqual((ended.event_at_ns, ended.body[-1]), (90_000_000, 'EXPIRED'))
        self.assertEqual(result.state.episode_incident_pA_ns, 200_000_000)
        self.assertIsNone(result.state.lease)
        self.assertEqual(result.state.phase, 'STOPPED')

    def test_stop_exactly_at_expiry_retains_stop_reason_and_invalidates_authority(self):
        self.owner(expiry=90_000_000); self.start()
        result = self.engine.tick(90_000_000, EpisodeInputs(stop=SafetyStop('stop', self.auth)))
        ended = next(f for f in result.facts if f.kind == 'RASTER_END')
        self.assertEqual(ended.body[-1], 'STOP')
        self.assertEqual(result.state.stop_generation, 1)
        self.assertIsNone(result.state.lease)

    def test_late_wakeup_starts_only_one_actual_successor_and_no_catchup_dose(self):
        self.owner(); start = self.start(request=ScanRequest(16, 16, 2e-6, 0., 0., 1000))
        result = self.engine.tick(500_000_000)
        self.assertEqual((len(result.ended_raster_ids), len(result.started_raster_ids), result.state.sweep_index), (1, 1, 1))
        self.assertEqual(result.state.episode_incident_pA_ns, 16*16*1000*10)
        self.assertEqual(next(f for f in result.facts if f.kind == 'RASTER_START').event_at_ns, 500_000_000)

    def test_configure_changes_only_next_raster_and_retains_global_dose(self):
        self.owner(); original = self.start(request=ScanRequest(64, 64, 2e-6, 0., 0., 1000))
        old = original.state.current_configuration
        changed = self.engine.tick(51_000_000, EpisodeInputs(normal=ConfigureLive('zoom', self.auth,
            ScanRequest(32, 16, 4e-6, .2e-6, -.1e-6, 8000), 0)))
        self.assertEqual(changed.state.current_configuration, old)
        self.assertNotEqual(changed.state.requested_configuration, old)
        boundary = self.engine.tick(100_000_000)
        self.assertEqual(boundary.state.episode_incident_pA_ns, 64*64*1000*10)
        self.assertIsNone(boundary.state.current_configuration)
        new = self.engine.tick(101_000_000, EpisodeInputs(bank_result=self.ready(boundary.bank_dispatch)))
        self.assertEqual(new.state.current_configuration.geometry.width_px, 32)
        self.assertEqual(new.state.current_configuration.geometry.field_width_m, 4e-6)
        self.assertEqual(new.state.episode_incident_pA_ns, boundary.state.episode_incident_pA_ns)

    def test_stage_stop_freezes_actual_pose_and_next_request_binds_it(self):
        self.owner()
        self.engine.tick(0, EpisodeInputs(normal=MoveStage('move', self.auth, .002, .001, 0)))
        moving = self.engine.tick(1_000_000_000)
        self.assertEqual(moving.state.phase, 'MOVING')
        self.assertGreater(moving.state.stage_x_m, 0.)
        self.assertLess(moving.state.stage_x_m, .002)
        stopped = self.engine.tick(1_200_000_000, EpisodeInputs(stop=SafetyStop('stop', self.auth)))
        x, y = stopped.state.stage_x_m, stopped.state.stage_y_m
        self.assertEqual(stopped.state.phase, 'STOPPED')
        self.assertEqual(stopped.state.episode_incident_pA_ns, 0)
        self.assertEqual((self.engine.tick(2_500_000_000).state.stage_x_m, self.engine.snapshot().stage_y_m), (x, y))
        new = self.engine.tick(2_500_000_000, EpisodeInputs(normal=StartCapture('capture', self.auth, 'SINGLE',
            ScanRequest(16, 16, 2e-6, 0., 0., 1000), 1)))
        self.assertEqual((new.bank_dispatch.configuration.geometry.stage_x_m, new.bank_dispatch.configuration.geometry.stage_y_m), (x, y))

    def test_exposure_and_motion_remain_mutually_exclusive(self):
        self.owner(); self.start()
        result = self.engine.tick(71_000_000, EpisodeInputs(normal=MoveStage('move', self.auth, .001, 0., 0)))
        self.assertEqual(result.state.phase, 'CAPTURING')
        self.assertEqual(result.state.stage_x_m, 0.)
        self.assertTrue(any(f.kind == 'DISPOSITION' and f.body[2] == 'BUSY_SESSION' for f in result.facts))

    def test_freeze_finishes_existing_sweep_and_no_successor(self):
        self.owner(); self.start(request=ScanRequest(16, 16, 2e-6, 0., 0., 1000))
        view = self.engine.snapshot().live_view_id
        self.engine.tick(71_000_000, EpisodeInputs(normal=FreezeLive('freeze', self.auth, view, 0)))
        result = self.engine.tick(100_000_000)
        self.assertEqual(result.state.phase, 'STOPPED')
        self.assertEqual(result.started_raster_ids, ())
        self.assertEqual(result.state.episode_incident_pA_ns, 16*16*1000*10)
        self.assertTrue(any(f.kind == 'SESSION_ENDED' and f.body[2] == 'freeze' for f in result.facts))

    def test_terminal_credit_and_emergency_control_survive_normal_exhaustion(self):
        self.owner(capacity=EpisodeCapacity(6, 7, 1, 18, 100, 100))
        # No verification ACKs:bootstrap control facts consume ordinary credits.
        result = self.engine.tick(0, EpisodeInputs(normal=StartCapture('start', self.auth, 'LIVE',
            ScanRequest(16, 16, 2e-6, 0., 0., 1000), 0)))
        self.assertEqual(result.state.phase, 'INTERLOCKED')
        self.assertTrue(result.state.beam_blank)
        self.assertTrue(any(f.kind == 'INTERLOCK' and f.emergency for f in result.facts))
        self.assertEqual(result.state.episode_incident_pA_ns, 0)

    def test_numeric_fault_blanks_at_actual_service_cut_and_stop_still_wins(self):
        self.owner(); self.start()
        result = self.engine.tick(71_000_000, EpisodeInputs(stop=SafetyStop('stop', self.auth),
            fault=EpisodeFault('episode1', 'NUMERIC_FAILURE')))
        self.assertTrue(result.state.beam_blank)
        self.assertEqual(result.state.phase, 'INTERLOCKED')
        self.assertEqual(result.state.stop_generation, 1)
        self.assertEqual(next(f for f in result.facts if f.kind == 'RASTER_END').body[-1], 'STOP')
        self.assertTrue(any(f.kind == 'DISPOSITION' and f.body[:2] == ('stop', 'ACCEPTED') for f in result.facts))

    def test_expiry_new_grant_and_late_capacity_failure_use_separate_control_reserves(self):
        self.owner(expiry=100_000_000, capacity=EpisodeCapacity(100, 7, 10, 100, 100, 100))
        self.start(mode='SINGLE', request=ScanRequest(16, 16, 2e-6, 0., 0., 1000))
        next_authority = AuthorityRef('next', 2)
        result = self.engine.tick(300_000_000, EpisodeInputs(
            authority=GrantAuthority('new-grant', 'next', 10**12),
            normal=MoveStage('move', next_authority, .001, 0., 0)))
        self.assertEqual(result.state.phase, 'INTERLOCKED')
        self.assertEqual(result.state.stage_x_m, 0.)
        leases = [f for f in result.facts if f.kind == 'LEASE']
        self.assertEqual(len(leases), 3)
        self.assertEqual([f.emergency for f in leases], [False, False, True])
        self.assertEqual(result.state.episode_incident_pA_ns, 16*16*1000*10)

    def test_invalid_future_ack_does_not_mutate_clock_or_physical_state(self):
        self.owner(); self.start()
        before = self.engine.snapshot()
        with self.assertRaises(ValueError):
            self.engine.tick(100_000_000, EpisodeInputs(verified_ack=VerifiedAcknowledgement('episode1', 99999)))
        self.assertEqual(before, self.engine.snapshot())

    def test_range_guard_never_teleports_stage_or_shortens_application_delay(self):
        self.owner(expiry=SAFE_INTEGER)
        result = self.engine.tick(SAFE_INTEGER-100, EpisodeInputs(normal=MoveStage('move', self.auth, .025, .025, 0)))
        self.assertEqual((result.state.stage_x_m, result.state.stage_y_m, result.state.phase), (0., 0., 'STOPPED'))
        self.assertTrue(any(f.kind == 'DISPOSITION' and f.body[2] == 'TIME_RANGE' for f in result.facts))
        self.assertEqual(self.engine.tick(SAFE_INTEGER).state.phase, 'INTERLOCKED')

    def test_merged_and_physical_predecessors_are_distinct_and_contiguous(self):
        first = self.owner()
        started = self.start()
        advanced = self.engine.tick(71_000_000)
        facts = list(first.facts)+list(started.facts)+list(advanced.facts)
        # The omitted admission/READY batches contain controls;global ordinal
        # values intentionally need not be consecutive in this selected subset.
        physical = [f for f in facts if f.physical_sequence is not None]
        self.assertEqual([f.physical_sequence for f in physical], [1, 2])
        self.assertTrue(all(f.physical_predecessor == f.physical_sequence-1 for f in physical))
        self.assertTrue(all(f.ordinal > f.physical_sequence for f in physical))


if __name__ == '__main__':
    unittest.main()
