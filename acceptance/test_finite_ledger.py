"""Actual causal facts/count law with an independently specified flat edge.

This constant-material mathematical fixture qualifies accounting and transaction
semantics. The stored-world/GPU optics and actual transport are separate gates.
"""
from dataclasses import replace
import hashlib
import math
import struct
import unittest
from unittest.mock import patch
import numpy as np
from engine import human_episode_types as t
from engine.beam_profile import ELEMENTARY_CHARGE_C
from engine.episode_credits import EpisodeCapacity
from engine.interactive_stage_episode import GroundedEpisode
from engine.human_photon_prefix import CountProcess,PROTOCOL
from engine.finite_probe_types import FiniteProfile,FiniteProbeBank
from engine.human_mapped_probe import effective_settings
from engine.finite_absorption import finite_absorption
from engine.finite_source import ResolvedFiniteSource
from engine.finite_image_ledger import EpisodeExposureLedger

SEED=b'finite-edge-count-test'.ljust(32,b'!');NAMESPACE='finite-charge-test'
BOUNDS=(-1e-4,0.,-1e-4,1e-4);INITIAL=t.EpisodeSettings(100,0.,0.,0.)


class FlatFiniteRegistry:
    def __init__(self):
        self.science=t.ScienceIdentity(FiniteProfile().profile_id,'1'*64,'2'*64,'VECTOR','3'*64,PROTOCOL)
        self.sources={}

    def prepare(self,ticket):
        geometry=ticket.configuration.geometry;settings=ticket.settings;beam=effective_settings(settings,geometry)
        p=[];e=[]
        for i in range(geometry.pixel_count):
            x,y=geometry.pixel_center(i);mass=finite_absorption(FiniteProfile().covariance(beam,0.),x,y,BOUNDS)
            p.append(mass.absorbed_probability);e.append(mass.escaped_probability)
        p=np.array(p);e=np.array(e);identity=hashlib.sha256(repr((geometry._key(),settings._key())).encode()).hexdigest()
        bank=FiniteProbeBank(geometry,settings,identity,.22*p,.077*p,np.zeros(geometry.pixel_count),0.,0.,1,p,e)
        handle=t.ScalarBankHandle('flat-'+str(len(self.sources)+1),1,identity,self.science.solver_source_digest,geometry,settings)
        self.sources[handle.handle_id]=ResolvedFiniteSource(handle,bank,25e-9,BOUNDS)
        return t.BankReady(ticket,handle)

    def resolve(self,handle):
        source=self.sources[handle.handle_id]
        if source.handle!=handle:raise ValueError('rebound flat fixture')
        return source


class Probe:
    def __init__(self):
        self.registry=FlatFiniteRegistry();self.engine=GroundedEpisode(self.registry.science,INITIAL,
            episode_namespace=NAMESPACE,capacity=EpisodeCapacity(4096,128,128,4096,512,512))
        self.ledger=self.fresh();self.facts=[]
        result=self.tick(0,t.EpisodeInputs(authority=t.GrantAuthority('grant','human',10**12)))
        self.authority=result.state.lease.authority

    def fresh(self):
        return EpisodeExposureLedger(self.registry.science,INITIAL,episode_namespace=NAMESPACE,
            seed=SEED,bank_resolver=self.registry.resolve,bounds_m=BOUNDS)

    def tick(self,at,inputs=t.EpisodeInputs()):
        inputs=replace(inputs,verified_ack=t.VerifiedAcknowledgement(NAMESPACE,self.ledger.last))
        result=self.engine.tick(at,inputs);receipt=self.ledger.ingest(result.facts)
        if receipt.status!='COMMITTED':raise AssertionError(receipt)
        self.facts.extend(result.facts);return result

    def start(self,offset=0.):
        request=t.ScanRequest(3,2,1.5e-6,offset,0.,2_000_000)
        result=self.tick(0,t.EpisodeInputs(normal=t.StartCapture('start',self.authority,'SINGLE',request,0)))
        ready=self.registry.prepare(result.bank_dispatch);self.handle=ready.handle
        self.tick(1,t.EpisodeInputs(bank_result=ready));opened=self.tick(50_000_000)
        return opened.started_raster_ids[0]

    def finish(self):return self.tick(50_000_000+self.engine.capture.plan.program_end_ns)


class FiniteLedgerTests(unittest.TestCase):
    def test_vacuum_counts_dose_and_ground_zero_but_incident_and_escape_continue(self):
        p=Probe();identifier=p.start(.002);p.finish();prefix=p.ledger.capture_prefix(identifier)
        self.assertEqual(prefix.outcome,'COMPLETED');self.assertGreater(prefix.incident_total_pA_ns,0)
        self.assertEqual(prefix.counts.read(0,6),(bytes(24),bytes(24)))
        dose=p.ledger.dose_snapshot();charge=dose.charge
        self.assertEqual((dose.cells,dose.unresolved_specimen_charge_C,charge.absorbed_charge_C,charge.ground_charge_C),((),0.,0.,0.))
        self.assertAlmostEqual(charge.escaped_primary_charge_C,charge.incident_charge_C,delta=8*math.ulp(charge.incident_charge_C))
        self.assertEqual(charge.incident_pA_ns,p.engine.snapshot().episode_incident_pA_ns)

    def test_half_edge_and_full_material_counts_match_independent_analytic_means(self):
        p=Probe();identifier=p.start();p.finish();prefix=p.ledger.capture_prefix(identifier)
        raw=prefix.counts.read(0,6);q=2_000_000*100/1e21
        for i,interception in enumerate((1.,.5,0.,1.,.5,0.)):
            for channel,coefficient,means,data in (('SE',.077,prefix.se_means,raw[0]),('BSE',.044,prefix.bse_means,raw[1])):
                expected=q/ELEMENTARY_CHARGE_C*(coefficient*interception)
                self.assertEqual(means[i],expected)
                self.assertEqual(struct.unpack_from('<I',data,i*4)[0],CountProcess(SEED,NAMESPACE+':'+identifier,i,channel).count(expected))
        charge=p.ledger.charge_snapshot();self.assertAlmostEqual(charge.absorbed_charge_C,3*q,delta=8*math.ulp(6*q))
        self.assertAlmostEqual(charge.escaped_primary_charge_C,3*q,delta=8*math.ulp(6*q))
        self.assertAlmostEqual(charge.ground_charge_C,3*q*(1-.22-.22),delta=8*math.ulp(6*q))
        dose=p.ledger.dose_snapshot()
        self.assertTrue(all((c.index_x+1)*dose.cell_size_m<=0. for c in dose.cells))

    def test_observer_fragmentation_preserves_exact_counts_charge_and_spatial_dose(self):
        a,b=Probe(),Probe();ia,ib=a.start(),b.start()
        for at in (70_000_001,70_000_019,70_700_000,72_001_337,74_500_000):b.tick(at)
        a.finish();b.finish();pa,pb=a.ledger.capture_prefix(ia),b.ledger.capture_prefix(ib)
        self.assertEqual(pa.counts.read(0,6),pb.counts.read(0,6));self.assertEqual(pa.se_means,pb.se_means)
        ca,cb=a.ledger.charge_snapshot(),b.ledger.charge_snapshot()
        for key in ('incident_charge_C','absorbed_charge_C','escaped_primary_charge_C','ground_charge_C'):
            self.assertEqual(getattr(ca,key),getattr(cb,key))
        da,db=a.ledger.dose_snapshot(),b.ledger.dose_snapshot();self.assertEqual(da.cells,db.cells)
        self.assertEqual(da.unresolved_specimen_charge_C,db.unresolved_specimen_charge_C)

    def test_transaction_rejection_does_not_change_new_charge_accumulators(self):
        p=Probe();p.start();p.tick(70_500_000);last=p.facts[-1]
        replay=p.fresh();receipt=replay.ingest(tuple(f for f in p.facts if f.ordinal<last.ordinal))
        self.assertEqual(receipt.status,'COMMITTED');before=replay.charge_snapshot()
        self.assertEqual(last.kind,'PREFIX')
        with patch('engine.human_fast_mapped_ledger.CountProcess.count',side_effect=ValueError('independent injected count failure')):
            receipt=replay.ingest((last,))
        self.assertEqual(receipt.status,'POISONED');self.assertEqual(replay.charge_snapshot(),before)


if __name__=='__main__':unittest.main()
