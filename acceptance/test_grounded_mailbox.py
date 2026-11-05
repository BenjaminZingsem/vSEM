"""Actual spawned-process semaphore visibility/death and closed-cell negatives."""
from dataclasses import replace
import multiprocessing as mp
import struct
import time
import unittest

from engine.episode_types import (EpisodeInputs, EpisodeFault, EpisodeSettings, AuthorityRef,
    SafetyStop, MoveStage, SetOptics, ScanRequest, StartCapture, GrantAuthority,
    ScienceIdentity, BankTicket, ScalarBankHandle, BankReady, VerifiedAcknowledgement)
from engine.episode_facts import EpisodeFact
from runtime.grounded_mailbox import ScalarMailbox, CELL_BYTES
from runtime.grounded_scalar_codec import encode_cell, decode_cell, HEADER_BYTES

NONCE = bytes(range(16))


def produce_cells(mailbox, completed, count):
    for number in range(1, count+1):
        inputs = EpisodeInputs(normal=MoveStage('move-'+str(number), AuthorityRef('human', 1),
            number/100000., -number/100000., number))
        cell = encode_cell(inputs, NONCE, number)
        deadline = time.monotonic()+20
        while not mailbox.try_put(cell):
            if time.monotonic() > deadline:
                raise RuntimeError('actual producer visibility witness stalled')
            time.sleep(.0005)
    completed.set()


def abandon_producer_slot(mailbox, acquired, exit_gate):
    if not mailbox._free.acquire(False):
        raise RuntimeError('test producer could not reserve its owned slot')
    memoryview(mailbox._storage).cast('B')[:37] = bytes([177])*37
    acquired.set()
    exit_gate.wait(10)
    # Deliberately no committed release:an actual dying producer owns this slot.


def abandon_consumer_slot(mailbox, acquired, exit_gate):
    if not mailbox._committed.acquire(False):
        raise RuntimeError('test consumer could not acquire committed owned slot')
    acquired.set()
    exit_gate.wait(10)
    # Deliberately no free release:an actual dying consumer owns this slot.


class ClosedCellTests(unittest.TestCase):
    def value(self):
        return EpisodeInputs(authority=GrantAuthority('grant', 'human', 300_000_000_000),
            normal=SetOptics('focus', AuthorityRef('human', 1), EpisodeSettings(10, -0., .18, -.12)),
            stop=SafetyStop('stop', AuthorityRef('human', 1)))

    def test_roundtrip_preserves_exact_closed_types_and_negative_zero(self):
        original = self.value()
        cell = encode_cell(original, NONCE, 1)
        self.assertEqual(len(cell), CELL_BYTES)
        result = decode_cell(cell, NONCE, 1)
        self.assertEqual(result, original)
        self.assertEqual(result.normal.settings.focus_offset_m.hex(), (-0.).hex())
        self.assertIs(type(result.normal.settings), EpisodeSettings)

    def test_real_ticket_and_ready_are_scalar_only_roundtrips(self):
        science = ScienceIdentity('profile', 'a'*64, 'b'*64, 'VECTOR', 'c'*64, 'count')
        config = ScanRequest(4096, 2048, 80e-6, 0., 0., 8000).bind(0., 0.)
        ticket = BankTicket('job', 'request', 'INITIAL_CAPTURE', AuthorityRef('human', 1),
            1, 0, 1, 0, 1, science, config, EpisodeSettings(10), 50_000_000)
        ready = BankReady(ticket, ScalarBankHandle('handle', 1, 'd'*64, 'c'*64, config.geometry, ticket.settings))
        for number, value in enumerate((ticket, ready), 1):
            self.assertEqual(decode_cell(encode_cell(value, NONCE, number), NONCE, number), value)

    def test_foreign_nonce_sequence_magic_version_and_reserved_bytes_reject(self):
        cell = encode_cell(self.value(), NONCE, 7)
        for nonce, sequence in ((bytes(16), 7), (NONCE, 6), (NONCE, 8)):
            with self.subTest(sequence=sequence), self.assertRaises(ValueError):
                decode_cell(cell, nonce, sequence)
        for offset in (0, 8, 64, 71):
            bad = bytearray(cell); bad[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                decode_cell(bytes(bad), NONCE, 7)

    def test_padding_tag_extra_body_and_truncation_are_not_accepted(self):
        cell = encode_cell(EpisodeInputs(), NONCE, 1)
        for malformed in (cell[:-1], cell+b'\x00', bytearray(cell), memoryview(cell)):
            with self.subTest(kind=type(malformed)), self.assertRaises(ValueError):
                decode_cell(malformed, NONCE, 1)
        for offset in (10, CELL_BYTES-1, HEADER_BYTES):
            bad = bytearray(cell); bad[offset] = 255
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                decode_cell(bytes(bad), NONCE, 1)
        bad = bytearray(cell)
        length = struct.unpack_from('<I', bad, 12)[0]
        struct.pack_into('<I', bad, 12, length+1)
        with self.assertRaises(ValueError):
            decode_cell(bytes(bad), NONCE, 1)

    def test_unknown_graph_dict_seed_and_mutable_inputs_never_encode(self):
        for value in ({'seed': 'private'}, [], b'private-seed', object(), ('arbitrary',)):
            with self.subTest(kind=type(value)), self.assertRaises(ValueError):
                encode_cell(value, NONCE, 1)
        for sequence in (True, -1, 0, 2**53):
            with self.subTest(sequence=sequence), self.assertRaises(ValueError):
                encode_cell(EpisodeInputs(), NONCE, sequence)

    def test_integer_encoding_cannot_impersonate_normalized_binary64_field(self):
        import runtime.grounded_scalar_codec as codec
        # The scalar constructors accept literal0,but their stored fields are
        # normalized float0. A wire int0 at a float position is noncanonical.
        inputs = EpisodeInputs(normal=SetOptics('focus', AuthorityRef('human', 1), EpisodeSettings(10)))
        cell = bytearray(encode_cell(inputs, NONCE, 1))
        needle = b'\x03'+struct.pack('<d', 0.)
        position = cell.find(needle, HEADER_BYTES)
        self.assertGreaterEqual(position, HEADER_BYTES)
        cell[position:position+9] = b'\x02'+struct.pack('<Q', 0)
        with self.assertRaises(ValueError):
            decode_cell(bytes(cell), NONCE, 1)

    def test_fact_header_source_provenance_must_equal_body(self):
        fact = EpisodeFact(1, 0, 200, 100, 'episode', 'C', False, None, None, 'INTERLOCK', ('PROCESS_FAILURE',))
        cell = encode_cell(fact, NONCE, 1)
        self.assertEqual(decode_cell(cell, NONCE, 1), fact)
        for offset in (48, 56):
            changed = bytearray(cell); changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                decode_cell(bytes(changed), NONCE, 1)


class ActualMailboxTests(unittest.TestCase):
    def setUp(self):
        self.context = mp.get_context('spawn')
        self.children = []

    def tearDown(self):
        for child in self.children:
            if child.is_alive():
                child.terminate()
            child.join(10)
            self.assertFalse(child.is_alive())
            child.close()

    def child(self, function, args):
        process = self.context.Process(target=function, args=args)
        process.start(); self.children.append(process)
        return process

    def test_actual_spawned_producer_wraps_without_partial_visibility(self):
        mailbox = ScalarMailbox(self.context, 7)
        completed = self.context.Event()
        process = self.child(produce_cells, (mailbox, completed, 512))
        deadline = time.monotonic()+30
        for number in range(1, 513):
            cell = None
            while cell is None:
                self.assertLess(time.monotonic(), deadline)
                cell = mailbox.try_get()
                if cell is None:
                    time.sleep(.0005)
            result = decode_cell(cell, NONCE, number)
            self.assertEqual(result.normal.operation_id, 'move-'+str(number))
            self.assertEqual(result.normal.expected_stop_generation, number)
            self.assertEqual(result.normal.x_m, number/100000.)
            self.assertEqual(result.normal.y_m, -number/100000.)
        self.assertTrue(completed.wait(10))
        process.join(10); self.assertEqual(process.exitcode, 0)
        self.assertIsNone(mailbox.try_get())

    def test_full_empty_and_bad_cell_do_not_change_credit(self):
        mailbox = ScalarMailbox(self.context, 1)
        self.assertIsNone(mailbox.try_get())
        for value in (b'', bytes(CELL_BYTES-1), bytearray(CELL_BYTES), None):
            with self.subTest(kind=type(value)), self.assertRaises(ValueError):
                mailbox.try_put(value)
        first = encode_cell(EpisodeInputs(), NONCE, 1)
        second = encode_cell(EpisodeFault('episode', 'PROCESS_FAILURE'), NONCE, 2)
        self.assertTrue(mailbox.try_put(first)); self.assertFalse(mailbox.try_put(second))
        self.assertEqual(mailbox.try_get(), first)
        self.assertTrue(mailbox.try_put(second)); self.assertEqual(mailbox.try_get(), second)

    def test_actual_producer_death_does_not_publish_partial_or_return_reserved_slot(self):
        mailbox = ScalarMailbox(self.context, 1)
        acquired, exit_gate = self.context.Event(), self.context.Event()
        process = self.child(abandon_producer_slot, (mailbox, acquired, exit_gate))
        self.assertTrue(acquired.wait(10))
        process.terminate(); process.join(10)
        self.assertFalse(process.is_alive())
        self.assertIsNone(mailbox.try_get())
        self.assertFalse(mailbox.try_put(encode_cell(EpisodeInputs(), NONCE, 1)))

    def test_actual_consumer_death_does_not_return_unreleased_slot(self):
        mailbox = ScalarMailbox(self.context, 1)
        self.assertTrue(mailbox.try_put(encode_cell(EpisodeInputs(), NONCE, 1)))
        acquired, exit_gate = self.context.Event(), self.context.Event()
        process = self.child(abandon_consumer_slot, (mailbox, acquired, exit_gate))
        self.assertTrue(acquired.wait(10))
        process.terminate(); process.join(10)
        self.assertFalse(process.is_alive())
        self.assertIsNone(mailbox.try_get())
        self.assertFalse(mailbox.try_put(encode_cell(EpisodeInputs(), NONCE, 2)))


if __name__ == '__main__':
    unittest.main()
