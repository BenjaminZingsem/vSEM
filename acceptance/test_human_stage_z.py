"""Independent scalar XYZ trajectories and genuine Z-coupled acquired counts.

Offline ticks are explicitly fixtures;real-process and visual release gates remain.
"""
from dataclasses import replace
import math
import unittest

from acceptance.test_human_episode_numerics import RealNumericalProbe
from engine.human_episode_types import (EpisodeGeometry, EpisodeInputs, EpisodeSettings,
    MoveStageXYZ, MoveStage, SetOptics, StartCapture, ScanRequest, SafetyStop,
    GrantAuthority, BankTicket, BankReady, ScalarBankHandle)
from engine.human_grounded_episode import GroundedEpisode
from engine.episode_credits import EpisodeCapacity
from runtime.human_scalar_codec import encode_cell, decode_cell
from runtime.grounded_scalar_codec import decode_cell as old_decode

class HumanStageZTests(unittest.TestCase):
    def probe(self, settings=None):
        return RealNumericalProbe(settings)

    def move(self, p, x=0., y=0., z=0., at=0, op='xyz'):
        return p.tick(at, EpisodeInputs(normal=MoveStageXYZ(op,p.authority,x,y,z,p.engine.stop_generation)))

    def test_xyz_duration_uses_slower_axis_and_actual_stop_pose(self):
        p=self.probe(); opened=self.move(p,x=.0001,y=-.0001,z=10e-6)
        fact=next(f for f in opened.facts if f.kind=='MOTION_XYZ_START')
        self.assertEqual(fact.body[-2:],(500_000_000,580_000_000))
        state=p.tick(250_000_000).state
        self.assertEqual((state.stage_x_m,state.stage_y_m,state.stage_z_m),(.00005,-.00005,5e-6))
        self.assertTrue(state.beam_blank)
        stopped=p.tick(300_000_000,EpisodeInputs(stop=SafetyStop('stop',p.authority)))
        self.assertEqual(stopped.state.phase,'STOPPED')
        self.assertEqual(stopped.state.stage_z_m,6e-6)
        self.assertEqual(stopped.state.episode_incident_pA_ns,0)
        after=p.tick(900_000_000).state
        self.assertEqual((after.stage_x_m,after.stage_y_m,after.stage_z_m),
            (stopped.state.stage_x_m,stopped.state.stage_y_m,stopped.state.stage_z_m))
        self.assertEqual(p.ledger.dose_snapshot().incident_total_pA_ns,0)

    def test_expiry_freezes_xyz_at_exact_known_deadline(self):
        p=self.probe()
        # A fresh owner receives a real scalar lease fixture expiring mid motion.
        p.engine=GroundedEpisode(p.registry.science,EpisodeSettings(10,1.2e-6,.18,-.12),
            episode_namespace='expiry',capacity=EpisodeCapacity(4096,128,128,4096,512,512))
        p.engine.tick(0,EpisodeInputs(authority=GrantAuthority('grant','human',100_000_000)))
        auth=p.engine.snapshot().lease.authority
        p.engine.tick(0,EpisodeInputs(normal=MoveStageXYZ('move',auth,.0001,0.,10e-6,0)))
        result=p.engine.tick(900_000_000)
        self.assertAlmostEqual(result.state.stage_z_m,2e-6,delta=1e-21)
        self.assertIsNone(result.state.lease)
        self.assertTrue(result.state.beam_blank)
        self.assertEqual(next(f.event_at_ns for f in result.facts if f.kind=='MOTION_XYZ_END'),100_000_000)

    def test_settling_then_new_capture_binds_actual_z_without_lens_rewrite(self):
        p=self.probe(); self.move(p,z=4e-6)
        settling=p.tick(200_000_000).state
        self.assertEqual(settling.phase,'MOVING')
        self.assertEqual(settling.stage_z_m,4e-6)
        self.assertTrue(settling.beam_blank)
        p.tick(280_000_000)
        opened=p.start(ScanRequest(3,2,1e-6,0.,0.,1000),at=300_000_000)
        geometry=opened.state.current_configuration.geometry
        self.assertEqual(geometry.stage_z_m,4e-6)
        self.assertEqual(opened.state.settings.focus_offset_m,1.2e-6)
        source=p.registry.resolve(next(f.body[7] for f in opened.facts if f.kind=='RASTER_START'))
        self.assertEqual(source.response(0).settings.focus_offset_m,1.2e-6+4e-6)

    def test_real_acquired_counts_and_dose_restore_with_lens_z_compensation(self):
        reference=self.probe(EpisodeSettings(10,2**-20,.18,-.12))
        translated=self.probe(EpisodeSettings(10,2**-20-2**-18,.18,-.12))
        self.move(translated,z=2**-18)
        translated.tick(300_000_000)
        request=ScanRequest(3,2,1e-6,0.,0.,1000)
        a=reference.start(request,at=400_000_000).started_raster_ids[0]
        b=translated.start(request,at=400_000_000).started_raster_ids[0]
        end=450_000_000+reference.engine.capture.plan.program_end_ns
        reference.tick(end);translated.tick(end)
        left,right=reference.ledger.capture_prefix(a),translated.ledger.capture_prefix(b)
        self.assertEqual(left.counts.read(0,6),right.counts.read(0,6))
        self.assertEqual(tuple(v.hex() for v in left.se_means),tuple(v.hex() for v in right.se_means))
        self.assertEqual(reference.ledger.dose_snapshot().cells,translated.ledger.dose_snapshot().cells)
        self.assertEqual(left.configuration.geometry.stage_z_m,0.)
        self.assertEqual(right.configuration.geometry.stage_z_m,2**-18)

    def test_real_response_probe_changes_with_z_at_same_lens_setting(self):
        a,b=self.probe(),self.probe()
        self.move(b,z=12e-6);b.tick(700_000_000)
        request=ScanRequest(2,2,1e-6,0.,0.,1000)
        x=a.start(request,at=800_000_000)
        y=b.start(request,at=800_000_000)
        ra=a.registry.resolve(next(f.body[7] for f in x.facts if f.kind=='RASTER_START')).response(0)
        rb=b.registry.resolve(next(f.body[7] for f in y.facts if f.kind=='RASTER_START')).response(0)
        self.assertGreater(rb.primary_covariance.principal_variances_m2()[1],
                           20*ra.primary_covariance.principal_variances_m2()[1])
        self.assertNotEqual(ra.se_collected_per_incident.hex(),rb.se_collected_per_incident.hex())

    def test_concurrent_capture_and_stage_xyz_is_rejected(self):
        p=self.probe();p.start(ScanRequest(64,32,2e-6,0.,0.,1_000_000))
        result=self.move(p,z=2e-6,at=71_000_000)
        self.assertEqual(result.state.stage_z_m,0.)
        self.assertTrue(any(f.kind=='DISPOSITION' and f.body[2]=='BUSY_SESSION' for f in result.facts))
        self.assertGreater(result.state.episode_incident_pA_ns,0)

    def test_combined_defocus_is_rejected_before_motion_or_lens_mutation(self):
        p=self.probe(EpisodeSettings(10,20e-6))
        result=self.move(p,z=10e-6)
        self.assertEqual(result.state.phase,'STOPPED')
        self.assertTrue(any(f.kind=='DISPOSITION' and f.body[2]=='SOURCE_DOMAIN' for f in result.facts))
        self.move(p,z=-10e-6,op='safe')
        result=p.tick(1,EpisodeInputs(normal=SetOptics('unsafe-optics',p.authority,EpisodeSettings(10,-20e-6))))
        self.assertIsNone(result.state.requested_settings)
        self.assertTrue(any(f.kind=='DISPOSITION' and f.body[2]=='SOURCE_DOMAIN' for f in result.facts))

    def test_z_ranges_signed_zero_and_xy_bind_are_strict(self):
        for value in (True,float('nan'),20.0001e-6,-20.0001e-6):
            with self.assertRaises(ValueError):
                EpisodeGeometry(1024,1024,20e-6,stage_z_m=value)
        a=EpisodeGeometry(1024,1024,20e-6,stage_z_m=0.)
        b=EpisodeGeometry(1024,1024,20e-6,stage_z_m=-0.)
        self.assertNotEqual(a,b)
        self.assertEqual(a.pixel_center(1048575),b.pixel_center(1048575))
        self.assertEqual(ScanRequest(1024,1024,20e-6,0.,0.,1000).bind(0.,0.,5e-6).geometry.stage_z_m,5e-6)

    def test_new_private_v3_rejects_cross_protocol_and_keeps_exact_xyz(self):
        p=self.probe(); value=EpisodeInputs(normal=MoveStageXYZ('move',p.authority,.0001,0.,-0.,0))
        nonce=bytes(range(16));cell=encode_cell(value,nonce,1)
        actual=decode_cell(cell,nonce,1)
        self.assertEqual(actual.normal.z_m.hex(),(-0.).hex())
        with self.assertRaises(ValueError):old_decode(cell,nonce,1)
        with self.assertRaises(ValueError):decode_cell(cell,bytes(16),1)

    def test_lens_application_after_stage_binds_current_pose(self):
        p=self.probe();opened=p.start(ScanRequest(2,2,1e-6,0.,0.,1000))
        end=50_000_000+p.engine.capture.plan.program_end_ns;p.tick(end)
        old=p.ledger.capture_prefix(opened.started_raster_ids[0])
        self.move(p,z=3e-6,at=100_000_000);p.tick(400_000_000)
        result=p.tick(401_000_000,EpisodeInputs(normal=SetOptics('lens',p.authority,EpisodeSettings(10,2e-6,.18,-.12))))
        self.assertEqual(result.bank_dispatch.configuration.geometry.stage_z_m,3e-6)
        self.assertEqual(old.configuration.geometry.stage_z_m,0.)

if __name__=='__main__':
    unittest.main()
