"""Opt-in actual finite GPU/HTTP command-image association acceptance."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from examples.agent_client import InstrumentClient
from runtime.finite_human_service import FiniteHumanService
from runtime.finite_launch_spec import FrozenFiniteLaunch
from runtime.hierarchical_http import HierarchicalHTTP


@unittest.skipUnless(os.environ.get('VSEM_TEST_CATALOGUE'), 'explicit GPU/catalogue integration test')
class AssociationGPUAcceptance(unittest.TestCase):
    def test_native1024_live_configure_freeze_and_cancelled_delivery(self):
        with tempfile.TemporaryDirectory(prefix='vsem-association-') as directory:
            service = http = client = None
            try:
                service = FiniteHumanService(Path(directory)/'episode', finite_catalogue=FrozenFiniteLaunch(
                    os.environ['VSEM_TEST_CATALOGUE'], os.environ['VSEM_TEST_CATALOGUE_SHA256']))
                http = HierarchicalHTTP(service)
                client = InstrumentClient(http.api.origin, http.api.token)
                client.acquire_control()

                def wait(condition, timeout=1800):
                    deadline = time.monotonic()+timeout
                    while time.monotonic() < deadline:
                        if client.renewal_error:
                            raise RuntimeError('Lease renewal failed') from client.renewal_error
                        state = client.request('/state')
                        self.assertNotEqual(state.get('availability'), 'QUARANTINED')
                        self.assertNotEqual(state.get('phase'), 'INTERLOCKED')
                        value = condition(state)
                        if value:
                            return value
                        time.sleep(.05)
                    self.fail('Actual association condition did not finish')

                def projection(operation):
                    return client.request('/operation/'+operation['operation_id']+'/acquisitions')

                def final(operation):
                    return wait(lambda _: projection(operation)['final_cut'])

                def scan(pixels, dwell=20000):
                    return dict(width_px=pixels, height_px=pixels, field_width_m=2e-6,
                        offset_x_m=0., offset_y_m=0., dwell_ns=dwell)

                def check_cut(cut, pixels):
                    metadata = client.request('/image/'+cut['image_id'])
                    self.assertEqual((metadata['source_id'], metadata['cut_elapsed_ns'], metadata['outcome']),
                        (cut['source_id'], cut['cut_elapsed_ns'], cut['outcome']))
                    with service.lock:
                        ready, _ = service.image_records[cut['image_id']]
                    self.assertEqual(ready.causal_raster_id, cut['raster_id'])
                    raw = client.request('/image/'+cut['image_id']+'/SE', raw=True)
                    self.assertEqual(len(raw), pixels*pixels*4)
                    for name in ('seed', 'ideal_focus', 'world_height', 'solver', 'descriptor', 'pid', 'ticket'):
                        self.assertNotIn(name, json.dumps(cut)+json.dumps(metadata))
                    return metadata

                client.wait_operation(client.command('optics', dict(current_pA=100,
                    focus_offset_m=0., stigmator_x=0., stigmator_y=0.)), 600)
                begun = time.monotonic()
                single = client.command('scan_single', scan(1024))
                wait(lambda s: s.get('progress') and 1024*1024//5 < s['progress']['completed_pixels'] < 1024*1024*4//5)
                optics = client.command('optics', dict(current_pA=100,
                    focus_offset_m=4e-6, stigmator_x=0., stigmator_y=0.))
                client.wait_operation(optics, 600)
                partial = wait(lambda _: (v if (v := projection(single))['latest_cut']
                    and v['latest_cut']['outcome'] == 'ACQUIRING' else None))
                self.assertIsNone(partial['final_cut'])
                self.assertEqual(partial['latest_cut']['raster_id'], partial['association']['raster_id'])
                partial_meta = check_cut(partial['latest_cut'], 1024)
                self.assertLess(partial_meta['completed_pixels'], 1024*1024)
                client.wait_operation(single, 1800)
                terminal = final(single)
                metadata = check_cut(terminal, 1024)
                self.assertEqual(terminal['raster_id'], projection(single)['association']['raster_id'])
                self.assertEqual(terminal['outcome'], 'COMPLETED')
                self.assertEqual(metadata['completed_pixels'], 1024*1024)
                self.assertGreaterEqual(time.monotonic()-begun, 1024*1024*20000/1e9)
                self.assertTrue({0., 4e-6}.issubset({s['focus_offset_m'] for s in metadata['parameter_segments']}))

                live = client.command('scan_live', scan(64, 1000000))
                wait(lambda s: s.get('current_scan') and s['current_scan']['width_px'] == 64
                    and s.get('progress') and s['progress']['completed_pixels'] > 0)
                original = projection(live)['association']
                configure = client.command('configure_live', scan(128, 100000))
                client.wait_operation(configure, 600)
                configured = projection(configure)
                self.assertEqual(configured['association']['relation'], 'configuration_applied')
                self.assertNotEqual(configured['association']['raster_id'], original['raster_id'])
                wait(lambda s: s.get('current_scan') and s['current_scan']['width_px'] == 128)
                source = projection(live)['association']['source_id']
                freeze = client.command('freeze', {'source_id': source})
                client.wait_operation(freeze, 600)
                client.wait_operation(live, 600)
                frozen = final(freeze)
                self.assertEqual(frozen, final(live))
                self.assertEqual(frozen['raster_id'], projection(freeze)['association']['raster_id'])
                self.assertEqual(projection(freeze)['association']['relation'], 'freeze_of')
                self.assertEqual(projection(configure)['association'], configured['association'])
                check_cut(frozen, 128)

                cancelled = client.command('scan_single', scan(128, 1000000))
                wait(lambda s: s.get('progress') and 0 < s['progress']['completed_pixels'] < 128*128//2)
                generation = client.request('/state')['stop_generation']
                client.wait_operation(client.command('stop', {}), 600)
                wait(lambda s: s['beam_blank'] and s['stop_generation'] > generation)
                result = final(cancelled)
                self.assertEqual(result['outcome'], 'CANCELLED')
                self.assertEqual(projection(cancelled)['receipt']['status'], 'CANCELLED')
                self.assertNotEqual(result['source_id'], terminal['source_id'])
                check_cut(result, 128)
                for old in (single, configure, live, freeze):
                    self.assertNotEqual(projection(old)['final_cut']['source_id'], result['source_id'])
            finally:
                try:
                    if client is not None:
                        client.close()
                finally:
                    if http is not None:
                        http.close()
                    if service is not None:
                        service.close()
                        self.assertFalse(service.thread.is_alive())
                        self.assertFalse(service.kernel.numeric.is_alive())
                        self.assertFalse(service.kernel.owner.is_alive())


if __name__ == '__main__':
    unittest.main()
