"""Independent image binding/failure contracts; authored HTTP data, no fibsem import."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'integrations/fibsemos/src'
if SOURCE.is_dir():
    sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(Path(__file__).resolve().parent))
QUALIFICATION = ROOT/'integrations/fibsemos/qualification'
if QUALIFICATION.is_dir():
    sys.path.insert(0, str(QUALIFICATION))
from image_fixture import COUNTS, ImageFixture, metadata
from vsem_fibsemos.client import Client
from vsem_fibsemos.errors import (AdmissionUnknown, AuthorityError, OperationFailure,
                                  PendingOutcome, ProtocolError, QualificationRequired)
from vsem_fibsemos.image_result import AcquisitionResult
from vsem_fibsemos.protocol import acquisitions, decode, raster
from vsem_fibsemos.records import RawFrame, canonical

SETTINGS = dict(width_px=64, height_px=64, hfw_m=2e-6, dwell_s=20e-6)


def observed():
    meta = metadata(raster(SETTINGS))
    cut = dict(image_id=meta['image_id'], source_id=meta['source_id'],
               raster_id=meta['source_id'], cut_elapsed_ns=meta['cut_elapsed_ns'], outcome='COMPLETED')
    value = dict(protocol='vsem.operation-acquisitions.v1', operation_id='op-7', command='scan_single',
        receipt=dict(operation_id='op-7', status='COMPLETED', reason='OK', observed_at_ns=10),
        association=dict(relation='started_single', source_id=meta['source_id'],
                         raster_id=meta['source_id'], applied_at_ns=0),
        latest_cut=dict(cut), final_cut=dict(cut))
    return meta, value


class AssociationParserTests(unittest.TestCase):
    def test_exact_closed_keys_and_defensive_copies(self):
        _, value = observed()
        copy = acquisitions(value, 'op-7', 'scan_single')
        copy['receipt']['status'] = 'UNKNOWN'
        copy['association']['source_id'] = 'other'
        copy['final_cut']['image_id'] = 'other'
        self.assertEqual(value['receipt']['status'], 'COMPLETED')
        self.assertNotEqual(value['association']['source_id'], 'other')
        self.assertNotEqual(value['final_cut']['image_id'], 'other')

    def test_unknown_missing_and_private_fields_are_rejected_at_every_level(self):
        _, original = observed()
        for layer in (None, 'receipt', 'association', 'final_cut', 'latest_cut'):
            target = original if layer is None else original[layer]
            for removed in list(target)+[None]:
                value = deepcopy(original)
                changed = value if layer is None else value[layer]
                if removed is None:
                    changed['seed'] = 'forbidden'
                else:
                    del changed[removed]
                with self.subTest(layer=layer, removed=removed), self.assertRaises(ProtocolError):
                    acquisitions(value, 'op-7')

    def test_wrong_protocol_identity_action_relation_raster_and_cut_types(self):
        _, original = observed()
        changes = [(None, 'protocol', 'other'), (None, 'operation_id', 'op-other'),
            (None, 'command', 'scan_live'), ('receipt', 'operation_id', 'op-other'),
            ('association', 'relation', 'live_session'), ('association', 'applied_at_ns', True),
            ('association', 'source_id', 'raster-other'), ('final_cut', 'raster_id', 'other'),
            ('final_cut', 'source_id', 'other'), ('final_cut', 'cut_elapsed_ns', -1),
            ('final_cut', 'cut_elapsed_ns', 4.), ('final_cut', 'image_id', '../private'),
            ('final_cut', 'outcome', 'ACQUIRING'), ('latest_cut', 'outcome', 'invented')]
        for layer, key, item in changes:
            value = deepcopy(original)
            (value if layer is None else value[layer])[key] = item
            with self.subTest(layer=layer, key=key, value=item), self.assertRaises(ProtocolError):
                acquisitions(value, 'op-7', 'scan_single')

    def test_null_unstarted_and_non_acquisition_are_allowed_without_invented_cut(self):
        _, value = observed()
        value.update(association=None, latest_cut=None, final_cut=None)
        value['receipt']['status'] = 'ACCEPTED'
        self.assertIsNone(acquisitions(value, 'op-7')['association'])
        value['command'] = 'lease'
        self.assertEqual(acquisitions(value, 'op-7')['command'], 'lease')
        value['final_cut'] = observed()[1]['final_cut']
        with self.assertRaises(ProtocolError):
            acquisitions(value, 'op-7')

    def test_old_live_sweep_latest_is_explicit_but_final_must_be_final_raster(self):
        _, value = observed()
        value['command'] = 'scan_live'
        value['association'].update(relation='live_session', raster_id='new-raster')
        value['final_cut'] = None
        self.assertNotEqual(acquisitions(value, 'op-7')['latest_cut']['raster_id'], 'new-raster')
        value['final_cut'] = dict(value['latest_cut'])
        with self.assertRaises(ProtocolError):
            acquisitions(value, 'op-7')

    def test_duplicate_json_keys_and_nonfinite_values_never_reach_a_parser(self):
        for raw in (b'{"command":"scan_single","command":"lease"}', b'{"x":1e999}', b'{"x":NaN}'):
            with self.assertRaises(ProtocolError):
                decode(raw)


class ImmutableImageResultTests(unittest.TestCase):
    def result(self, *, vacuum=False):
        meta, association = observed()
        raw = bytes(4096*4) if vacuum else struct.pack('<8I', *COUNTS)*512
        frame = RawFrame.from_observation(raw, meta)
        return AcquisitionResult.from_acquisition(frame, association, 9, 101, raster(SETTINGS))

    def test_fixed_window_hand_calculated_counts_and_lossless_raw(self):
        result = self.result()
        self.assertEqual(struct.unpack('<8H', result.view_bytes[:16]),
                         (0, 0, 65535, 65535, 65535, 65535, 64110, 0))
        self.assertEqual(struct.unpack('<8I', result.raw_frame.raw[:32]), COUNTS)
        self.assertEqual(result.view_provenance['orientation'], 'columns_positive_x_rows_negative_y')
        self.assertFalse(result.view_provenance['lossless_counts'])
        self.assertTrue(result.view_provenance['raw_companion_required'])

    def test_exact_raw_roundtrip_and_all_acquisition_time_segments(self):
        result = self.result()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'counts.vsem'
            result.raw_frame.save(path)
            again = RawFrame.load(path)
        self.assertEqual(again, result.raw_frame)
        self.assertEqual([s['focus_offset_m'] for s in again.metadata['parameter_segments']], [0., 4e-6])
        self.assertEqual(len(again.metadata['blank_holds']), 1)

    def test_vacuum_does_not_require_auto_window_or_invent_signal(self):
        result = self.result(vacuum=True)
        self.assertEqual(result.raw_frame.raw, bytes(4096*4))
        self.assertEqual(result.view_bytes, bytes(4096*2))

    def test_result_fields_immutable_and_nested_observations_are_copies(self):
        result = self.result()
        with self.assertRaises(FrozenInstanceError):
            result.view_bytes = b'edited'
        value = result.association
        value['association']['source_id'] = 'edited'
        transform = result.view_provenance
        transform['black'] = 99
        self.assertNotEqual(result.association['association']['source_id'], 'edited')
        self.assertEqual(result.view_provenance['black'], 9)

    def test_altered_view_or_provenance_cannot_claim_a_raw_companion(self):
        result = self.result()
        for change in (dict(view_bytes=b'\1'+result.view_bytes[1:]),
                       dict(provenance_bytes=canonical(dict(result.view_provenance, filtering='hidden'))),
                       dict(association_bytes=canonical(dict(result.association, operation_id='other')))):
            with self.subTest(change=list(change)), self.assertRaises((ProtocolError, ValueError)):
                replace(result, **change)

    def test_wrong_metadata_geometry_dwell_coverage_or_cut_is_not_an_image_result(self):
        for changes in (dict(cut_elapsed_ns=99), dict(completed_pixels=4095),
                dict(active_dwell_ns=1), dict(outcome='CANCELLED'), dict(terminal_reason='STOP'),
                dict(mode='LIVE'), dict(field_width_m=3e-6), dict(offset_x_m=1e-6), dict(dwell_ns=100000)):
            meta, association = observed()
            meta.update(changes)
            frame = RawFrame.from_observation(bytes(4096*4), meta)
            with self.subTest(changes=changes), self.assertRaises(ProtocolError):
                AcquisitionResult.from_acquisition(frame, association, 0, 100, raster(SETTINGS))


class ImageTransportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ImageFixture()
        self.client = Client(self.fixture.origin, 'qualification-fixture-only', timeout_s=.5, poll_s=.005)

    def tearDown(self):
        self.fixture.release_raw.set()
        self.client.close()
        self.fixture.close()

    def ready(self):
        self.client.configure_image_return(0, 65535)
        self.client.acquire_control()

    def test_default_refusal_and_single_use_policy_validate_without_network(self):
        with self.assertRaises(QualificationRequired):
            self.client.acquire_image(SETTINGS)
        for black, white in ((False, 100), (0, True), (9, 9), (-1, 2), (0, 2**32)):
            with self.assertRaises(ValueError):
                self.client.configure_image_return(black, white)
        self.client.configure_image_return(0, 100)
        with self.assertRaises(RuntimeError):
            self.client.configure_image_return(1, 200)
        self.assertEqual(self.fixture.paths, [])

    def test_legacy_or_malformed_probe_refuses_before_exposure(self):
        self.ready()
        self.fixture.enabled = False
        with self.assertRaises(QualificationRequired):
            self.client.acquire_image(SETTINGS)
        self.fixture.enabled = True
        self.fixture.probe_overrides['seed'] = 'untrusted'
        with self.assertRaises(ProtocolError):
            self.client.acquire_image(SETTINGS)
        self.assertEqual(self.fixture.commands, [])

    def test_exact_image_and_raw_result_without_latest_image_or_private_reads(self):
        self.ready()
        result = self.client.acquire_image(SETTINGS)
        self.assertIsInstance(result, AcquisitionResult)
        self.assertEqual(len(self.fixture.commands), 1)
        op = result.association['operation_id']
        self.assertEqual(self.fixture.commands[0]['action'], 'scan_single')
        self.assertIn('/operation/'+op+'/acquisitions', self.fixture.paths)
        self.assertTrue(all(not any(word in path for word in ('truth', 'latest', 'owner.cells')) for path in self.fixture.paths))

    def test_completion_before_delivery_times_out_and_reconciles_same_exposure(self):
        self.ready()
        self.fixture.allow_publication.clear()
        with self.assertRaises(PendingOutcome) as pending:
            self.client.acquire_image(SETTINGS, .03)
        op = pending.exception.operation_id
        self.assertEqual(self.client.operation(op)['status'], 'COMPLETED')
        with self.assertRaises(PendingOutcome):
            self.client.acquire_image(SETTINGS, .03)
        self.assertEqual(len(self.fixture.commands), 1)
        self.fixture.allow_publication.set()
        result = self.client.reconcile_image(op, .5)
        self.assertEqual(result.association['operation_id'], op)
        self.assertEqual(len(self.fixture.commands), 1)

    def test_get_loss_retains_known_id_and_does_not_replay(self):
        self.ready()
        self.fixture.fail_next_association = True
        with self.assertRaises(PendingOutcome) as pending:
            self.client.acquire_image(SETTINGS)
        result = self.client.reconcile_image(pending.exception.operation_id)
        self.assertEqual(result.association['operation_id'], pending.exception.operation_id)
        self.assertEqual(len(self.fixture.commands), 1)

    def test_unknown_admission_stays_halted_without_a_replayed_command(self):
        self.ready()
        self.fixture.drop_next_command = True
        with self.assertRaises(AdmissionUnknown):
            self.client.acquire_image(SETTINGS)
        with self.assertRaises(AdmissionUnknown):
            self.client.acquire_image(SETTINGS)
        self.assertEqual(len(self.fixture.commands), 1)

    def test_wrong_source_raster_and_metadata_fail_with_known_id_and_no_substitution(self):
        self.ready()
        self.fixture.metadata_overrides['source_id'] = 'wrong-source'
        with self.assertRaises(PendingOutcome) as pending:
            self.client.acquire_image(SETTINGS)
        op = pending.exception.operation_id
        self.fixture.metadata_overrides.clear()
        self.fixture.association_overrides['final_cut'] = None
        with self.assertRaises(PendingOutcome):
            self.client.reconcile_image(op, .02)
        self.fixture.association_overrides.clear()
        self.assertEqual(self.client.reconcile_image(op).association['operation_id'], op)
        self.assertEqual(len(self.fixture.commands), 1)

    def test_cancelled_and_rejected_receipts_never_return_successful_images(self):
        self.ready()
        for outcome in ('CANCELLED', 'REJECTED', 'UNKNOWN'):
            self.fixture.receipt_status = outcome
            with self.subTest(outcome=outcome), self.assertRaises(OperationFailure) as failure:
                self.client.acquire_image(SETTINGS)
            self.assertEqual(failure.exception.receipt['status'], outcome)
            if outcome == 'UNKNOWN':
                break
        self.assertFalse(any(path.startswith('/image/') for path in self.fixture.paths))

    def test_reconciliation_cannot_change_the_admitted_request_or_window(self):
        self.ready()
        self.fixture.allow_publication.clear()
        with self.assertRaises(PendingOutcome) as pending:
            self.client.acquire_image(SETTINGS, .02)
        with self.assertRaises(ValueError):
            self.client.reconcile_image(pending.exception.operation_id, settings=dict(SETTINGS, hfw_m=3e-6))
        self.fixture.allow_publication.set()
        self.assertIsInstance(self.client.reconcile_image(pending.exception.operation_id), AcquisitionResult)

    def test_raw_truncation_and_interlock_are_explicit_without_new_exposure(self):
        self.ready()
        self.fixture.raw_override = b'truncated'
        with self.assertRaises(PendingOutcome) as pending:
            self.client.acquire_image(SETTINGS)
        self.fixture.state['interlock_reason'] = 'BANK_FAILED'
        with self.assertRaises(AuthorityError):
            self.client.reconcile_image(pending.exception.operation_id)
        self.assertEqual(len(self.fixture.commands), 1)

    def test_blocked_raw_get_does_not_hold_stop_or_lease_paths(self):
        self.ready()
        self.fixture.block_raw = True
        results = []
        def acquire():
            try:
                results.append(self.client.acquire_image(SETTINGS))
            except Exception as error:
                results.append(error)
        thread = threading.Thread(target=acquire)
        thread.start()
        try:
            self.assertTrue(self.fixture.raw_blocked.wait(2.))
            leases = self.fixture.leases
            self.client._renew_once()
            before = self.fixture.state['stop_generation']
            self.client.stop()
            self.assertGreater(self.fixture.leases, leases)
            self.assertGreater(self.fixture.state['stop_generation'], before)
            self.assertTrue(thread.is_alive())
        finally:
            self.fixture.release_raw.set()
            thread.join(3.)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(results[0], AcquisitionResult)
        self.assertEqual([c['action'] for c in self.fixture.commands], ['scan_single', 'stop'])


if __name__ == '__main__':
    unittest.main()
