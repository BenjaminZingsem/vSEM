"""Real pinned upstream image workflow, INSIDE approved public CPU isolation only."""
from contextlib import contextmanager
import hashlib
import inspect
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import traceback

sys.path.insert(0, '/tests')
from artifacts import require
from environment import inspect_environment
from genuine import actual_class, expect, settings, system
from image_fixture import COUNTS, ImageFixture
from processes import write_json

EVIDENCE = {}


@contextmanager
def connected(**options):
    fixture, microscope = ImageFixture(**options), None
    try:
        microscope = actual_class()(system('vSEM'))
        microscope.configure_api(fixture.origin, 'qualification-fixture-only')
        microscope.configure_image_return(9, 101)
        require(fixture.paths == [], 'image policy configuration caused network access')
        microscope.connect_to_microscope('127.0.0.1', fixture.server.server_port, reset_beam_shift=False)
        yield microscope, fixture
    finally:
        try:
            if microscope is not None:
                microscope.disconnect()
        finally:
            fixture.close()


def acquire(microscope, request):
    from fibsem.acquire import acquire_image
    return acquire_image(microscope, request)


def image_success():
    import numpy as np
    from fibsem.structures.image import FibsemImage, FibsemImageMetadata
    from fibsem.services.imaging import Imaging
    from vsem_fibsemos.records import RawFrame
    expected = np.array([0, 0, 65535, 65535, 65535, 65535, 64110, 0], dtype='<u2')
    results = []
    with connected(paced=True, publication_delay_s=.1) as (microscope, fixture):
        require(type(microscope.imaging) is Imaging, 'not the unchanged upstream Imaging service')
        for size in (256, 1024):
            request = settings(size)
            started = time.monotonic()
            image = acquire(microscope, request)
            elapsed = time.monotonic()-started
            result = image.vsem_result
            metadata = result.raw_frame.metadata
            op = result.association['operation_id']
            require(isinstance(image, FibsemImage) and type(image).__module__ == 'vsem_fibsemos.bindings',
                    'returned object is not a genuine upstream image subclass')
            require(Path(inspect.getfile(type(image))).is_relative_to(Path(sys.prefix)),
                    'image class imported from source bypass')
            require(isinstance(image.metadata, FibsemImageMetadata), 'not real upstream metadata')
            require(image.data.shape == (size, size) and image.data.dtype == np.dtype('uint16'),
                    'wrong compatibility view shape/dtype')
            require(np.array_equal(image.data.ravel(), np.tile(expected, size*size//8)),
                    'view differs from independently calculated fixed window')
            require(image.data.tobytes() == result.view_bytes, 'upstream constructor changed view data')
            require(image.filtered_data.shape == image.data.shape, 'upstream filtered display derivative missing')
            require(image.metadata.pixel_size.x == metadata['pixel_pitch_m'] and
                    image.metadata.pixel_size.y == metadata['pixel_pitch_m'], 'wrong acquired pixel pitch')
            require(image.metadata.microscope_state is None and image.metadata.hardware_geometry is None,
                    'unavailable microscope fields were fabricated')
            require(image.metadata.image_settings.resolution == request.resolution and
                    image.metadata.image_settings.hfw == request.hfw, 'request intent changed')
            require(image.metadata.acquisition_datetime is not None, 'unchanged upstream call stamp missing')
            require(elapsed >= metadata['cut_elapsed_ns']/1e9, 'fixture result served before its declared duration')
            raw = fixture.images[metadata['image_id']][1]
            require(result.raw_frame.raw == raw and result.raw_frame.digest == hashlib.sha256(raw).hexdigest(),
                    'raw uint32 counts changed')
            require(len(metadata['parameter_segments']) == 2 and len(metadata['blank_holds']) == 1,
                    'acquisition-time segments/holds were discarded')
            require(result.association['final_cut']['image_id'] == metadata['image_id'] and
                    result.association['association']['source_id'] == metadata['source_id'],
                    'association/raw source mismatch')
            with tempfile.TemporaryDirectory() as directory:
                destination = Path(directory)/'refused.tif'
                expect(NotImplementedError, lambda: image.save(destination))
                require(list(Path(directory).iterdir()) == [], 'refused view save touched filesystem')
                raw_path = Path(directory)/'raw.vsem'
                result.raw_frame.save(raw_path)
                loaded = RawFrame.load(raw_path)
                require(loaded == result.raw_frame, 'lossless raw roundtrip changed metadata or counts')
            results.append(dict(size=size, dtype=str(image.data.dtype), elapsed_s=elapsed,
                declared_duration_ns=metadata['cut_elapsed_ns'], raw_sha256=result.raw_frame.digest,
                view_sha256=result.view_sha256, association=result.association,
                view_provenance=result.view_provenance,
                auxiliary_filtered_data='upstream display derivative; not raw counts',
                wall_clock_stamp='upstream pre-driver call time; not episode exposure time',
                physics_qualified=False))
        require([c['action'] for c in fixture.commands] == ['scan_single', 'scan_single'],
                'upstream image workflow emitted extra commands')
    EVIDENCE['configured_images'] = results


def refusal_and_vacuum():
    from vsem_fibsemos.errors import ProtocolError, QualificationRequired
    with connected(vacuum=True) as (microscope, fixture):
        fixture.enabled = False
        expect(QualificationRequired, lambda: acquire(microscope, settings(256)))
        fixture.enabled = True
        fixture.probe_overrides['seed'] = 'forbidden'
        expect(ProtocolError, lambda: acquire(microscope, settings(256)))
        require(fixture.commands == [], 'legacy/malformed probe admitted exposure')
        fixture.probe_overrides.clear()
        request = settings(256)
        request.save = True
        expect(ValueError, lambda: acquire(microscope, request))
        require(fixture.commands == [], 'automatic save refusal exposed specimen')
        image = acquire(microscope, settings(256))
        require(not image.data.any() and image.vsem_result.raw_frame.raw == bytes(256*256*4),
                'vacuum gained artificial signal or autoscaling')
    EVIDENCE['before_exposure_refusals_and_vacuum'] = dict(status='PASS')


def reconciliation():
    from vsem_fibsemos.errors import PendingOutcome
    with connected() as (microscope, fixture):
        fixture.allow_publication.clear()
        # An explicit client timeout preserves the operation; the normal upstream
        # image workflow is qualified separately with its unchanged default wait.
        request = dict(width_px=256, height_px=256, hfw_m=80e-6, dwell_s=20e-6)
        try:
            microscope._client().acquire_image(request, .1)
        except PendingOutcome as error:
            operation = error.operation_id
        else:
            raise AssertionError('missing final delivery became success')
        require(microscope._client().operation(operation)['status'] == 'COMPLETED',
                'test did not separate physical completion from numerical delivery')
        expect(PendingOutcome, lambda: microscope._client().acquire_image(request, .1))
        require(len(fixture.commands) == 1, 'pending acquisition was replayed')
        fixture.allow_publication.set()
        image = microscope.reconcile_image(operation, settings(256), .5)
        require(image.vsem_result.association['operation_id'] == operation and len(fixture.commands) == 1,
                'reconciliation exposed again or selected a different command')
    EVIDENCE['reconciliation'] = dict(operation_id=operation, acquisition_commands=1)


def responsive_stop_and_lease():
    results = []
    with connected() as (microscope, fixture):
        fixture.block_raw = True
        def run():
            try:
                results.append(acquire(microscope, settings(256)))
            except Exception as error:
                results.append(error)
        thread = threading.Thread(target=run, name='genuine-image-wait')
        thread.start()
        try:
            require(fixture.raw_blocked.wait(5.), 'genuine upstream path did not request raw counts')
            deadline = time.monotonic()+8.
            while fixture.leases < 2 and time.monotonic() < deadline:
                time.sleep(.05)
            require(fixture.leases >= 2, 'real periodic renewal blocked behind image IO')
            generation = fixture.state['stop_generation']
            microscope.stop()
            require(fixture.state['stop_generation'] > generation and thread.is_alive(),
                    'Stop was blocked or not independently confirmed')
        finally:
            fixture.release_raw.set()
            thread.join(15.)
        require(not thread.is_alive() and len(results) == 1 and not isinstance(results[0], BaseException),
                'owned upstream acquisition failed or remained running')
        require([c['action'] for c in fixture.commands] == ['scan_single', 'stop'], 'unexpected replay')
        EVIDENCE['independent_stop_and_periodic_lease'] = dict(leases=fixture.leases,
            stop_generation=fixture.state['stop_generation'], acquisition_commands=1,
            timing='Stop during blocked delivery after fixture physical completion')


def failed_outcomes():
    from vsem_fibsemos.errors import AdmissionUnknown, AuthorityError, OperationFailure, PendingOutcome
    for status in ('CANCELLED', 'REJECTED', 'UNKNOWN'):
        with connected() as (microscope, fixture):
            fixture.receipt_status = status
            expect(OperationFailure, lambda: acquire(microscope, settings(256)))
            require(len(fixture.commands) == 1 and not any(p.startswith('/image/') for p in fixture.paths),
                    'failed operation became an image or was replayed')
    with connected() as (microscope, fixture):
        fixture.drop_next_command = True
        expect(AdmissionUnknown, lambda: acquire(microscope, settings(256)))
        expect(AdmissionUnknown, lambda: acquire(microscope, settings(256)))
        require(len(fixture.commands) == 1, 'unknown admission replayed')
    with connected() as (microscope, fixture):
        fixture.fail_next_association = True
        try:
            acquire(microscope, settings(256))
        except PendingOutcome as error:
            operation = error.operation_id
        else:
            raise AssertionError('lost GET was treated as a result')
        fixture.state['interlock_reason'] = 'BANK_FAILED'
        expect(AuthorityError, lambda: microscope.reconcile_image(operation, settings(256)))
        require(len(fixture.commands) == 1, 'interlock caused a retry or reset')
    EVIDENCE['failed_outcomes'] = dict(status='PASS')


def main():
    inspect_environment(include_built=True)
    results = []
    for name, operation in [('configured_genuine_images', image_success),
            ('refusals_and_vacuum', refusal_and_vacuum), ('explicit_reconciliation', reconciliation),
            ('independent_stop_and_lease', responsive_stop_and_lease), ('failed_outcomes', failed_outcomes)]:
        started = time.monotonic()
        try:
            operation()
            result = dict(name=name, status='PASS')
        except Exception:
            result = dict(name=name, status='FAIL', traceback=traceback.format_exc())
        result['elapsed_s'] = time.monotonic()-started
        results.append(result)
        write_json('/out/image-case-'+name+'.json', result)
    deadline = time.monotonic()+10.
    while len(threading.enumerate()) > 1 and time.monotonic() < deadline:
        time.sleep(.1)
    remaining = [t.name for t in threading.enumerate() if t is not threading.main_thread()]
    prohibited = sorted(n for n in sys.modules if n.startswith(('engine.', 'runtime.', 'evaluator.',
        'fibsem.ai.', 'torch', 'PyQt', 'PySide', 'autoscript_sdb_microscope_client')))
    results.append(dict(name='image_threads_and_import_boundary', status='FAIL' if remaining or prohibited else 'PASS',
                        remaining_threads=remaining, prohibited_imports=prohibited))
    EVIDENCE['results'] = results
    EVIDENCE['physics_qualified'] = False
    EVIDENCE['imported_modules'] = sorted(sys.modules)
    write_json('/out/genuine-image-results.json', EVIDENCE)
    return int(any(r['status'] != 'PASS' for r in results))


if __name__ == '__main__':
    sys.exit(main())
