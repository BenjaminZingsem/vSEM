"""Candidate real device subclasses for the pinned fibsemOS interfaces.

Independently authored from interface inspection. M05A does not import or execute
this module: genuine discovery, construction and unchanged service workflows are
M05B gates. No vendor SDK, hidden engine state, environment or config-token lookup.
"""
from dataclasses import fields

from fibsem.microscope import FibsemMicroscope
from fibsem.devices.beam import Beam
from fibsem.devices.stage import Stage
from fibsem.devices.core import BoundParameter, ParameterReadOnly, ParameterUnavailable
from fibsem.structures.params import ParameterMetadata, RangeLimit
from fibsem.structures.settings import BeamType, FibsemStagePosition, ImageSettings, Point
from fibsem.services.imaging import Imaging, bind_imaging

from .client import Client
from .preflight import FRAME, IMAGE_FIELDS, beam_write, image_request, stage_position
from .protocol import real
from .units import ns_to_dwell, pa_to_current


def unsupported(*args, **kwargs):
    raise NotImplementedError('operation is unavailable in the vSEM source prototype')


def _image_request(settings):
    if type(settings) is not ImageSettings or {f.name for f in fields(settings)} != set(IMAGE_FIELDS):
        raise ValueError('explicit pinned ImageSettings required')
    value = {name: getattr(settings, name) for name in IMAGE_FIELDS}
    if value['beam_type'] is not BeamType.ELECTRON:
        raise ValueError('only the electron beam is supported')
    value['beam_type'] = 'ELECTRON'
    return image_request(value)


def _beam_value(name, value):
    if name == 'stigmation':
        if type(value) is not Point:
            raise ValueError('explicit two-axis Point required')
        if value.name is not None:
            raise ValueError('named stigmation transforms are unsupported')
        mapped = beam_write(name, {'x': value.x, 'y': value.y})
        return Point(mapped['x'], mapped['y'])
    return beam_write(name, value)


class _StrictParameter(BoundParameter):
    def validate(self, value):
        # Direct beam.current.set_value(...) must not clip first.
        return _beam_value(self.name, value)

    def write_through(self, value):
        # Also cover upstream facade paths that bypass validate().
        return self.set_value(value)

    def set_value(self, value):
        value = self.validate(value)
        if not self.settable:
            raise ParameterReadOnly('parameter is read-only')
        with self.device._claim_write(self):
            self._write(value)
            actual = self._read()
        # Signal only observed state, never a cached requested setting. A failed
        # readback raises even if the command completed; it is not permission to retry.
        self.report(actual)
        self.device._dependency_changed(self.name)
        return actual


class VsemBeam(Beam):
    def __init__(self, client, parent):
        super().__init__(BeamType.ELECTRON, parent=parent)
        self._vsem_client = client

    def bind(self, name, read, write=None, metadata=None, needs_channel=False):
        if write is None:
            return super().bind(name, read, write, metadata, needs_channel)
        if name not in ('current', 'stigmation'):
            raise ValueError('unsupported writable parameter')
        parameter = _StrictParameter(self, self.declared_parameters()[name], read,
                                     write, metadata, needs_channel)
        self._bound[name] = parameter
        return parameter

    def read_current(self):
        return pa_to_current(self._vsem_client.state()['applied']['current_pA'])

    def write_current(self, value):
        self._vsem_client.set_optics({'current_a': beam_write('current', value)})

    def metadata_current(self):
        return ParameterMetadata(limits=RangeLimit(1e-12, 1e-9))

    def read_stigmation(self):
        applied = self._vsem_client.state()['applied']
        return Point(applied['stigmator_x'], applied['stigmator_y'])

    def write_stigmation(self, value):
        value = _beam_value('stigmation', value)
        self._vsem_client.set_optics({'stigmator_x': value.x, 'stigmator_y': value.y})

    def metadata_stigmation(self):
        return ParameterMetadata(limits={'x': RangeLimit(-1., 1.), 'y': RangeLimit(-1., 1.)})

    def _scan(self):
        scan = self._vsem_client.state().get('current_scan')
        if scan is None:
            raise ParameterUnavailable('no observed current raster; no requested/default fallback')
        return scan

    def read_hfw(self):
        return self._scan()['field_width_m']

    def metadata_hfw(self):
        return ParameterMetadata(limits=RangeLimit(1e-7, .005), settable=False)

    def read_resolution(self):
        scan = self._scan()
        return (scan['width_px'], scan['height_px'])

    def metadata_resolution(self):
        return ParameterMetadata(choices=tuple((n, n) for n in (64, 128, 256, 512, 1024)), settable=False)

    def read_dwell_time(self):
        return ns_to_dwell(self._scan()['dwell_ns'])

    def metadata_dwell_time(self):
        return ParameterMetadata(choices=(20e-6, 100e-6, .001), settable=False)

    def read_detector_type(self):
        if self._vsem_client.state().get('capabilities', {}).get('detectors') != ['SE']:
            raise ParameterUnavailable('SE capability is not observed')
        return 'SE'

    def metadata_detector_type(self):
        return ParameterMetadata(choices=('SE',), settable=False)

    def acquire(self, image_settings=None):
        _image_request(image_settings)
        # Preserve the upstream Beam/Imaging workflow after whole-request preflight.
        # _acquire refuses before exposure until public correlation exists.
        return super().acquire(image_settings)

    def _acquire(self, image_settings):
        return self._vsem_client.acquire_image(_image_request(image_settings))

    def available_live(self):
        return False

    def _has_auto_focus(self):
        return False

    start_live = unsupported
    stop_live = unsupported
    _set_bit_depth = unsupported
    _autocontrast = unsupported
    _auto_focus = unsupported


class VsemStage(Stage):
    frame = FRAME

    def __init__(self, client, parent):
        super().__init__(parent=parent)
        self._vsem_client = client

    def read_position(self):
        value = self._vsem_client.state()['stage']
        return FibsemStagePosition(x=value['x_m'], y=value['y_m'], z=value['z_m'],
                                   coordinate_system=FRAME)

    def metadata_position(self):
        return ParameterMetadata(limits={'x': RangeLimit(-.025, .025),
                                         'y': RangeLimit(-.025, .025),
                                         'z': RangeLimit(-20e-6, 20e-6)}, settable=False)

    def _move_absolute(self, position):
        if type(position) is not FibsemStagePosition:
            raise ValueError('explicit specimen position required')
        value = {key: getattr(position, key) for key in
                 ('name', 'x', 'y', 'z', 'r', 't', 'coordinate_system')}
        self._vsem_client.move_stage(stage_position(value))

    _move_relative = unsupported
    _home = unsupported
    _link = unsupported


def _builder_client(entry, context, *, electron=False):
    if type(context.microscope) is not VsemMicroscope:
        raise ValueError('builders require the explicitly configured vSEM facade')
    expected_name, expected_type = ('electron', 'beam') if electron else ('stage', 'stage')
    if (getattr(entry, 'name', None) != expected_name or
            getattr(entry, 'type', None) != expected_type or
            getattr(entry, 'enabled', None) not in (None, True) or
            getattr(entry, 'driver', None) not in (None, 'vSEM') or
            getattr(entry, 'roles', None) or getattr(entry, 'options', None)):
        raise ValueError('unsupported device entry; credentials never belong in configuration')
    return context.microscope._client()


def build_electron(entry, context):
    return VsemBeam(_builder_client(entry, context, electron=True), context.microscope).connect()


def build_stage(entry, context):
    return VsemStage(_builder_client(entry, context), context.microscope).connect()


class VsemMicroscope(FibsemMicroscope):
    def __init__(self, system):
        self.system = system
        self.driver_name = 'vSEM'
        self._vsem_api = None
        self._vsem_origin = None
        self._vsem_connected = False

    def configure_api(self, origin, token):
        if self._vsem_api is not None:
            raise RuntimeError('connection configuration is single-use')
        self._vsem_api = Client(origin, token)
        self._vsem_origin = origin

    def _client(self):
        if self._vsem_api is None:
            raise RuntimeError('configure_api(origin, token) explicitly before connection')
        return self._vsem_api

    def connect_to_microscope(self, ip_address, port, reset_beam_shift=True):
        client = self._client()
        if (type(ip_address) is not str or ip_address != '127.0.0.1' or type(port) is not int or
                self._vsem_origin != f'http://127.0.0.1:{port}' or reset_beam_shift is not False):
            raise ValueError('configured loopback endpoint and reset_beam_shift=False required')
        if self._vsem_connected:
            raise RuntimeError('already connected')
        if (self.system.apply_defaults_on_connect is not False or
                self.system.beams_on_at_connect is not False or
                self.system.other_devices or self.system.device_roles or self.system.device_entry_keys or
                self.system.ion.enabled is not False or self.system.manipulator.enabled is not False or
                self.system.fm.enabled is not False or
                self.system.electron.enabled is not True or self.system.stage.enabled is not True):
            raise ValueError('explicit electron/stage-only configuration without automatic writes required')
        # No generic configuration/plugin builder, defaults, beam-on or SDK path.
        # Bind locally first, then explicitly acquire control.
        beam = VsemBeam(client, self).connect()
        stage = VsemStage(client, self).connect()
        self._set_device('electron', beam)
        self._set_device('stage', stage)
        try:
            self.imaging = bind_imaging(Imaging, self)
            client.acquire_control()
        except Exception:
            self._set_device('electron', None)
            self._set_device('stage', None)
            raise
        self._vsem_connected = True

    def _disconnect(self):
        if self._vsem_api is not None:
            self._vsem_api.close()
        self._vsem_connected = False

    def _write_beam(self, name, value, beam_type):
        value = _beam_value(name, value)
        if beam_type is not BeamType.ELECTRON or not self._vsem_connected:
            raise ParameterUnavailable('electron device is unavailable')
        parameter = self._beam_parameter(name, beam_type)
        if parameter is None:
            raise ParameterUnavailable('beam parameter is unavailable')
        parameter.set_value(value)

    def get_focus_offset_m(self):
        return self._client().state()['applied']['focus_offset_m']

    def set_focus_offset_m(self, value):
        return self._client().set_optics({'focus_offset_m': real(value, -25e-6, 25e-6)})

    def stop(self):
        return self._client().stop()

    # Observable receipts, not a replacement upstream image workflow.
    def submit_scan(self, settings, mode='SINGLE'):
        return self._client().submit_scan(settings, mode)

    def freeze(self, source_id):
        return self._client().freeze(source_id)

    def get_state(self):
        return self._client().state()

    set_state = unsupported
    set_microscope_state = unsupported
    set_beam_settings = unsupported
    set_detector_settings = unsupported
    set_imaging_settings = unsupported
    apply_defaults = unsupported
    reset_beam_shifts = unsupported
    _switch_beam = unsupported
