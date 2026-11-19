"""Independent actual-upstream qualification; no fake classes or monkeypatches."""
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import importlib.metadata
import inspect
import json
import math
from pathlib import Path
import sys
import threading
import time
import traceback

sys.path.insert(0, '/tests')
from artifacts import require
from environment import inspect_environment
from observable_fixture import ObservableFixture
from processes import write_json

EVIDENCE = {}


def expect(kind, operation):
    try:
        operation()
    except kind:
        return
    raise AssertionError('required explicit refusal did not occur')


def system(manufacturer):
    from fibsem.structures.system import SystemSettings
    value = SystemSettings.from_dict({
        'info': {'manufacturer': manufacturer},
        'hardware': {'devices': [
            {'name': 'electron', 'type': 'beam', 'enabled': True},
            {'name': 'ion', 'type': 'beam', 'enabled': False},
            {'name': 'stage', 'type': 'stage', 'enabled': True},
            {'name': 'fm', 'type': 'fm', 'enabled': False}]},
        'defaults': {'apply_on_connect': False, 'beams_on_at_connect': False},
        'sim': {'has_fm': False, 'has_manipulator': False, 'sample': {'enabled': False}},
    })
    value.manipulator.enabled = False  # Explicit configuration, not a patched device/class.
    value.fm.enabled = False
    return value


def settings(size):
    from fibsem.structures.settings import BeamType, ImageSettings
    return ImageSettings(resolution=(size, size), dwell_time=20e-6, hfw=80e-6,
                         beam_type=BeamType.ELECTRON, autocontrast=False,
                         save=False, filename='qualification', path=None, reduced_area=None,
                         line_integration=None, scan_interlacing=None, frame_integration=None,
                         drift_correction=False, bit_depth=None)


def actual_class():
    points = importlib.metadata.entry_points(group='fibsem.drivers')
    require([(p.name, p.value) for p in points] == [('vsem', 'vsem_fibsemos.plugin:driver_entry')],
            'installed driver discovery allowlist mismatch')
    from fibsem.drivers.registry import DRIVER_PLUGINS
    plugins = DRIVER_PLUGINS.plugins()
    require(set(plugins) == {'vSEM'}, 'real registry did not discover exactly the approved plugin')
    entry = plugins['vSEM']
    cls = entry.load()
    from fibsem.microscope import FibsemMicroscope
    require(issubclass(cls, FibsemMicroscope) and cls.__module__ == 'vsem_fibsemos.bindings',
            'not a genuine upstream subclass')
    require(Path(inspect.getfile(cls)).is_relative_to(Path(sys.prefix)), 'plugin imported from source bypass')
    EVIDENCE['discovery'] = {'registry': inspect.getfile(type(DRIVER_PLUGINS)),
                              'microscope': inspect.getfile(cls), 'base': inspect.getfile(FibsemMicroscope),
                              'entry_points': [(p.name, p.value) for p in points]}
    return cls


@contextmanager
def connected():
    fixture, microscope = ObservableFixture(), None
    try:
        microscope = actual_class()(system('vSEM'))
        require(fixture.paths == [], 'construction attempted network access')
        microscope.configure_api(fixture.origin, 'qualification-fixture-only')
        require(fixture.paths == [], 'configuration attempted network access')
        microscope.connect_to_microscope('127.0.0.1', fixture.server.server_port, reset_beam_shift=False)
        yield microscope, fixture
    finally:
        try:
            if microscope is not None:
                microscope.disconnect()
        finally:
            fixture.close()


def discovery():
    from fibsem.devices.beam import Beam
    from fibsem.devices.stage import Stage
    from fibsem.services.imaging import Imaging
    from fibsem.structures.settings import BeamType
    with connected() as (microscope, fixture):
        require(isinstance(microscope.beams[BeamType.ELECTRON], Beam), 'real beam not constructed')
        require(isinstance(microscope.stage, Stage), 'real stage not constructed')
        require(type(microscope.imaging) is Imaging, 'unchanged Imaging service not bound')
        require(fixture.leases == 1 and fixture.commands == [], 'connection applied hidden defaults')


def bindings():
    from fibsem.structures.settings import BeamType, Point, FibsemStagePosition
    with connected() as (microscope, fixture):
        beam = microscope.beams[BeamType.ELECTRON]
        for pa in (1, 225, 1000):
            beam.current.set_value(pa * 1e-12)
            require(fixture.state['applied']['current_pA'] == pa, 'current unit conversion incorrect')
            require(math.isclose(beam.current.get_value(), pa * 1e-12, rel_tol=1e-12, abs_tol=0),
                    'current readback incorrect')
        microscope.set_focus_offset_m(4e-6)
        require(microscope.get_focus_offset_m() == 4e-6, 'relative focus readback incorrect')
        beam.stigmation.set_value(Point(-.3, .4))
        point = beam.stigmation.get_value()
        require((point.x, point.y) == (-.3, .4), 'stigmation readback incorrect')
        position = FibsemStagePosition(x=.002, y=-.003, z=2e-6, r=None, t=None,
                                      coordinate_system='vsem_specimen_xyz_m')
        microscope.stage.move_absolute(position)
        actual = microscope.stage.position.get_value()
        require((actual.x, actual.y, actual.z) == (.002, -.003, 2e-6), 'stage axes/units incorrect')
        require(actual.coordinate_system == 'vsem_specimen_xyz_m', 'stage frame changed')
        before = len(fixture.commands)
        for value in (True, '1e-10', float('nan'), .5e-12, 100.1e-12, 1.001e-9):
            expect(ValueError, lambda: beam.current.set_value(value))
        expect(ValueError, lambda: beam.stigmation.set_value(Point(1.001, 0)))
        expect(ValueError, lambda: microscope.set_focus_offset_m(30e-6))
        expect(ValueError, lambda: microscope.stage.move_absolute(FibsemStagePosition(
            x=0., y=0., z=0., r=.1, t=None, coordinate_system='vsem_specimen_xyz_m')))
        expect(NotImplementedError, lambda: microscope.apply_defaults())
        require(len(fixture.commands) == before, 'invalid or unsupported request caused a command')
        EVIDENCE['bindings'] = {'commands': fixture.commands, 'readback': microscope.get_state()}


def connection_refusals():
    cls = actual_class()
    fixture = ObservableFixture()
    try:
        for automatic in (None, 'apply_defaults_on_connect', 'beams_on_at_connect'):
            config = system('vSEM')
            if automatic:
                setattr(config, automatic, True)
            microscope = cls(config)
            try:
                if automatic is None:
                    expect(RuntimeError, lambda: microscope.connect_to_microscope(
                        '127.0.0.1', fixture.server.server_port, reset_beam_shift=False))
                microscope.configure_api(fixture.origin, 'qualification-fixture-only')
                if automatic:
                    expect(ValueError, lambda: microscope.connect_to_microscope(
                        '127.0.0.1', fixture.server.server_port, reset_beam_shift=False))
                else:
                    expect(ValueError, lambda: microscope.connect_to_microscope(
                        '127.0.0.1', fixture.server.server_port))
                require('qualification-fixture-only' not in repr(config), 'credential leaked into settings')
                require(fixture.paths == [], 'refused connection reached HTTP fixture')
            finally:
                microscope.disconnect()
    finally:
        fixture.close()


def authority_and_stop():
    from vsem_fibsemos.errors import AdmissionUnknown, PendingOutcome
    with connected() as (microscope, fixture):
        fixture.drop_next_command = True
        request = {'width_px': 256, 'height_px': 256, 'hfw_m': 80e-6, 'dwell_s': 20e-6}
        expect(AdmissionUnknown, lambda: microscope.submit_scan(request))
        expect(AdmissionUnknown, lambda: microscope.submit_scan(request))
        require(len(fixture.commands) == 1, 'unknown admission was replayed')
        before = fixture.state['stop_generation']
        microscope.stop()
        require(fixture.state['stop_generation'] == before + 1, 'Stop not independently confirmed')
        expect(AdmissionUnknown, lambda: microscope.submit_scan(request))
        require([c['action'] for c in fixture.commands] == ['scan_single', 'stop'], 'unexpected command replay')
        fixture.confirm_stop = False
        expect(PendingOutcome, lambda: microscope._client().stop(timeout_s=.1))
        EVIDENCE['uncertain_admission_and_stop'] = {'commands': fixture.commands,
                                                   'stop_generation': fixture.state['stop_generation']}


def lease_loss():
    from vsem_fibsemos.errors import AuthorityError
    with connected() as (microscope, fixture):
        fixture.change_epoch = True
        deadline = time.monotonic() + 15.
        while microscope._client()._renew_error is None and time.monotonic() < deadline:
            time.sleep(.05)
        require(fixture.leases >= 2, 'actual periodic lease renewal did not occur')
        expect(AuthorityError, lambda: microscope.set_focus_offset_m(1e-6))
        require(fixture.commands == [], 'lease loss permitted a write')
        EVIDENCE['lease'] = {'renewals': fixture.leases - 1, 'epoch': fixture.state['control']['epoch']}


def demo():
    from fibsem.drivers.demo.microscope import DemoMicroscope
    from fibsem.services.imaging import Imaging
    microscope = DemoMicroscope(system('Demo'))
    try:
        microscope.connect_to_microscope('127.0.0.1', reset_beam_shift=False)
        require(type(microscope.imaging) is Imaging, 'Demo Imaging service changed')
        results = []
        for size in (256, 1024):
            request = settings(size)
            start = time.monotonic()
            image = microscope.imaging.acquire_image(request)
            require(image.data.shape == (size, size), 'Demo image shape mismatch')
            require(str(image.data.dtype) in ('uint8', 'uint16'), 'unexpected Demo count dtype')
            require(image.data.max() > image.data.min(), 'Demo image lacks generated signal')
            observed = image.metadata.image_settings
            require(tuple(observed.resolution) == (size, size) and observed.hfw == request.hfw and
                    observed.dwell_time == request.dwell_time, 'Demo acquired settings mismatch')
            results.append({'shape': list(image.data.shape), 'dtype': str(image.data.dtype),
                            'sha256': hashlib.sha256(image.data.tobytes()).hexdigest(),
                            'hfw_m': observed.hfw, 'dwell_s': observed.dwell_time,
                            'elapsed_s': time.monotonic() - start, 'physics_qualified': False})
        EVIDENCE['demo'] = results
    finally:
        microscope.stop_acquisition()
        microscope.disconnect()


def honest_refusal():
    from fibsem.structures.settings import ImageSettings
    from vsem_fibsemos.errors import QualificationRequired
    with connected() as (microscope, fixture):
        for size in (256, 1024):
            expect(QualificationRequired, lambda: microscope.imaging.acquire_image(settings(size)))
        expect(ValueError, lambda: microscope.acquire_image(ImageSettings()))
        require(fixture.commands == [], 'unqualified acquisition exposed the sample')
        EVIDENCE['qualified_refusal'] = {'sizes': [256, 1024], 'command_count': 0}


def main():
    inspect_environment(include_built=True)
    results = []
    for gate, name, operation in [('C3', 'genuine_discovery', discovery), ('C4', 'supported_and_refused_bindings', bindings),
                                  ('C5', 'explicit_connection', connection_refusals),
                                  ('C5', 'uncertainty_no_replay_and_stop', authority_and_stop),
                                  ('C5', 'real_periodic_lease_loss', lease_loss),
                                  ('C6', 'unchanged_demo_256_and_1024', demo),
                                  ('C7', 'vsem_refuses_before_exposure', honest_refusal)]:
        start = time.monotonic()
        try:
            operation()
            result = {'gate': gate, 'name': name, 'status': 'PASS'}
        except Exception:
            result = {'gate': gate, 'name': name, 'status': 'FAIL', 'traceback': traceback.format_exc()}
        result['elapsed_s'] = time.monotonic() - start
        results.append(result)
        write_json('/out/case-' + name + '.json', result)
    deadline = time.monotonic() + 10.
    while len(threading.enumerate()) > 1 and time.monotonic() < deadline:
        time.sleep(.1)
    remaining = [t.name for t in threading.enumerate() if t is not threading.main_thread()]
    prohibited = sorted(n for n in sys.modules if n.startswith(('vsem.', 'apps.', 'runtime.', 'fibsem.ai.',
                                                                'torch', 'PyQt', 'PySide', 'autoscript_sdb_microscope_client')))
    results.append({'gate': 'C8', 'name': 'threads_and_import_boundary',
                    'status': 'FAIL' if remaining or prohibited else 'PASS',
                    'remaining_threads': remaining, 'prohibited_imports': prohibited})
    EVIDENCE['results'] = results
    EVIDENCE['imported_modules'] = sorted(sys.modules)
    write_json('/out/genuine-results.json', EVIDENCE)
    return int(any(r['status'] != 'PASS' for r in results))


if __name__ == '__main__':
    sys.exit(main())
