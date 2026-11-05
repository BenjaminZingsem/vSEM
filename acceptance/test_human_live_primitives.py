"""Scalar pacing fixtures and actual reserved-ring OS-process checks."""
from dataclasses import replace
import multiprocessing as mp
import time
import unittest

from engine import human_episode_types as t
from engine.episode_credits import EpisodeCapacity
from engine.human_paced_episode import GroundedEpisode
from runtime.human_paced_verifier import PacedCausalVerifier
from runtime.human_live_records import LiveTickBegin,SweepDelivery,NativeImageReady
from runtime.human_realtime_records import TickEnd
from runtime.human_live_codec import encode_cell,decode_cell
from runtime.human_realtime_codec import decode_cell as old_decode
from runtime.human_reserved_mailbox import ReservedMailbox
from runtime.human_live_kernel import RetainedSpool,emergency_cells,TICK_CELLS

SCIENCE = t.ScienceIdentity('fixture','a'*64,'b'*64,'VECTOR','c'*64,'count')
CAPACITY = EpisodeCapacity(256,28,8,256,1024,1024)


def produce_ring(mailbox,signal):
    terminal = mailbox.reserve(3)
    for value in range(512):
        while True:
            reservation = mailbox.reserve(2)
            if reservation is not None: break
            time.sleep(.001)
        reservation.commit(value.to_bytes(8,'little')+bytes([value%256])*4088)
        reservation.close()
    terminal.close(); signal.set()


def abandon_reservation(mailbox,signal):
    reservation = mailbox.reserve(3)
    if reservation is None: raise RuntimeError('Reservation absent')
    signal.set()
    while True: time.sleep(.1)


class PrimitiveTests(unittest.TestCase):
    def test_v5_is_closed_and_rejects_v4_nonce_and_private_graphs(self):
        value = LiveTickBegin(1,0,t.EpisodeInputs(),SweepDelivery('episode','raster-1',1))
        cell = encode_cell(value,bytes(16),1)
        self.assertEqual(decode_cell(cell,bytes(16),1),value)
        with self.assertRaises(ValueError): old_decode(cell,bytes(16),1)
        with self.assertRaises(ValueError): decode_cell(cell,bytes([1])*16,1)
        with self.assertRaises(ValueError): encode_cell({'rates':[1.]},bytes(16),1)
        image = NativeImageReady('image-1','raster-1',1,1,'d'*64)
        self.assertEqual(decode_cell(encode_cell(image,bytes(16),1),bytes(16),1),image)

    def probe(self):
        initial = t.EpisodeSettings(100)
        owner = GroundedEpisode(SCIENCE,initial,episode_namespace='episode',capacity=CAPACITY)
        verifier = PacedCausalVerifier(SCIENCE,initial,episode_namespace='episode',capacity=CAPACITY)
        number = 0
        def tick(at,inputs=t.EpisodeInputs(),delivery=None):
            nonlocal number
            inputs = replace(inputs,verified_ack=t.VerifiedAcknowledgement('episode',verifier.cut.last_ordinal if verifier.cut else 0))
            value = owner.tick(at,inputs,delivery); number += 1
            verifier.verify(LiveTickBegin(number,at,inputs,delivery),value.facts,
                TickEnd(number,value.state,value.bank_dispatch,value.started_raster_ids,value.ended_raster_ids))
            return value
        auth = tick(0,t.EpisodeInputs(authority=t.GrantAuthority('grant','human',10**12))).state.lease.authority
        submitted = tick(0,t.EpisodeInputs(normal=t.StartCapture('scan',auth,'LIVE',t.ScanRequest(1,1,1e-6,0.,0.,1000),0)))
        ticket = submitted.bank_dispatch
        ready = t.BankReady(ticket,t.ScalarBankHandle('handle',1,'d'*64,'c'*64,ticket.configuration.geometry,ticket.settings))
        tick(1,t.EpisodeInputs(bank_result=ready)); tick(50_000_000)
        tick(80_001_000)
        return owner,verifier,tick,auth

    def test_no_successor_until_exact_attested_delivery(self):
        owner,verifier,tick,_ = self.probe()
        prior = owner.total
        value = tick(1_000_000_000)
        self.assertEqual(value.state.phase,'BETWEEN_SWEEPS'); self.assertTrue(value.state.beam_blank)
        self.assertEqual(owner.total,prior)
        delivery = SweepDelivery('episode',owner.last_ended[0],owner.last_ended[1])
        verifier.register_delivery(delivery)
        value = tick(1_000_000_001,delivery=delivery)
        self.assertEqual(value.started_raster_ids,('raster-2',)); self.assertEqual(owner.total,prior)

    def test_unattested_valid_delivery_is_quarantined(self):
        owner,verifier,tick,_ = self.probe()
        delivery = SweepDelivery('episode',owner.last_ended[0],owner.last_ended[1])
        with self.assertRaises(ValueError): tick(81_000_000,delivery=delivery)
        self.assertIsNotNone(verifier.poison)

    def test_foreign_stale_future_and_stopped_deliveries_cannot_arm(self):
        owner,verifier,tick,auth = self.probe()
        for index,delivery in enumerate((SweepDelivery('foreign','raster-1',owner.last_ended[1]),
                SweepDelivery('episode','raster-99',owner.last_ended[1]),
                SweepDelivery('episode','raster-1',owner.last_ended[1]+1))):
            self.assertEqual(tick(81_000_000+index,delivery=delivery).started_raster_ids,())
        stopped = tick(82_000_000,t.EpisodeInputs(stop=t.SafetyStop('stop',auth)))
        self.assertEqual(stopped.state.phase,'STOPPED')
        delivery = SweepDelivery('episode',owner.last_ended[0],owner.last_ended[1]); verifier.register_delivery(delivery)
        self.assertEqual(tick(83_000_000,delivery=delivery).started_raster_ids,())

    def test_reserved_os_ring_wraps_without_overwriting_terminal_space(self):
        ctx = mp.get_context('spawn'); mailbox = ReservedMailbox(ctx,7); signal = ctx.Event()
        process = ctx.Process(target=produce_ring,args=(mailbox,signal)); process.start()
        try:
            received = [] ; deadline = time.perf_counter()+15.
            while len(received) < 512 and time.perf_counter() < deadline:
                cell = mailbox.try_get()
                if cell is None: time.sleep(.001); continue
                value = int.from_bytes(cell[:8],'little')
                self.assertEqual(cell[8:],bytes([value%256])*4088); received.append(value)
            self.assertEqual(received,list(range(512)))
            process.join(5.); self.assertEqual(process.exitcode,0); self.assertTrue(signal.is_set())
            reservation = mailbox.reserve(7); self.assertIsNotNone(reservation); reservation.close()
        finally:
            if process.is_alive(): process.kill(); process.join(5.)

    def test_dead_producer_reservation_is_never_reclaimed(self):
        ctx = mp.get_context('spawn'); mailbox = ReservedMailbox(ctx,7); signal = ctx.Event()
        process = ctx.Process(target=abandon_reservation,args=(mailbox,signal)); process.start()
        try:
            self.assertTrue(signal.wait(10.)); process.kill(); process.join(5.)
            self.assertIsNone(mailbox.try_get()); self.assertIsNone(mailbox.reserve(5))
            # Observer-only free-credit check;this is NOT a replacement producer.
            free = mailbox.reserve(4); self.assertIsNotNone(free); free.close()
        finally:
            if process.is_alive(): process.kill(); process.join(5.)

    def test_spool_releases_only_numerically_consumed_groups_and_has_full_reserve(self):
        reserve = emergency_cells(CAPACITY,1024)
        self.assertGreater(reserve,1024+3*sum((256,28,8,256))+TICK_CELLS)
        spool = RetainedSpool(3,reserve); cell = bytes(4096)
        spool.retain([cell]*2,10); spool.retain([cell]*2,20)
        self.assertTrue(spool.pressured); spool.consume(9); self.assertEqual(spool.cells,4)
        spool.consume(10); self.assertEqual(spool.cells,2)
        spool.consume(20); self.assertEqual(spool.cells,0)
        self.assertTrue(spool.pressured)  # permanent pressure fence,not auto restart


if __name__ == '__main__': unittest.main()
