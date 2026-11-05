"""Frontier-owned live command validation and public raster geometry.

No transport credentials, physical truth or specimen contents live here.
"""
import copy
import math
import re

SAFE_INTEGER = 9007199254740991
# Qualified host/reference-solver wall dwell. This is explicit admission, never
# a rewrite of requested physical acquisition time; v1 single scans are intact.
MIN_LIVE_WALL_DWELL_S = .002
GEOMETRY_ARGUMENTS = {'width_px', 'height_px', 'dwell_s', 'field_width_m',
                      'offset_x_m', 'offset_y_m'}


def validate_live_envelope(channel, envelope):
    if channel not in ('ui', 'instrument') or type(envelope) is not dict:
        raise ValueError('invalid_live_protocol')
    name, key, protocol = ('intent', 'intent_id', 'ui.live-intent.v1') if channel == 'ui' else (
        'command', 'idempotency_key', 'instrument.live-command.v1')
    if set(envelope) != {'protocol', key, 'lease_token', 'expected_revision', name, 'arguments'}:
        raise ValueError('invalid_live_protocol')
    if envelope['protocol'] != protocol:
        raise ValueError('wrong_live_transport')
    for field in (key, 'lease_token'):
        item = envelope[field]
        if type(item) is not str or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', item):
            raise ValueError('invalid_live_protocol')
    revision = envelope['expected_revision']
    if type(revision) is not int or not 0 <= revision <= SAFE_INTEGER:
        raise ValueError('invalid_live_revision')
    command, arguments = envelope[name], envelope['arguments']
    if type(command) is not str or command not in ('start_live', 'configure_live', 'capture_live', 'freeze_live'):
        raise ValueError('unsupported_live_command')
    if type(arguments) is not dict:
        raise ValueError('invalid_live_arguments')
    if command in ('capture_live', 'freeze_live'):
        if arguments:
            raise ValueError('invalid_live_arguments')
    else:
        if set(arguments) != GEOMETRY_ARGUMENTS:
            raise ValueError('invalid_live_geometry')
        for field in ('width_px', 'height_px'):
            if type(arguments[field]) is not int or not 1 <= arguments[field] <= 256:
                raise ValueError('invalid_live_geometry')
        for field, minimum, maximum in (
            ('dwell_s', 1e-8, 0.01), ('field_width_m', 1e-6, 0.005),
            ('offset_x_m', -0.005, 0.005), ('offset_y_m', -0.005, 0.005)):
            item = arguments[field]
            if type(item) not in (int, float) or not minimum <= item <= maximum or not math.isfinite(item):
                raise ValueError('invalid_live_geometry')
    return copy.deepcopy(envelope), command, key


def acquired_geometry(capture, generation):
    """Explicit projection of applied deflection, sampling and whole pixels."""
    t, s, live = capture['timing'], capture['settings'], capture['live']
    pixel = capture['field']/t.width_px
    completed = sum(capture['elapsed'] >= t.row_start_s(row)+(col+1)*t.dwell_s
                    for row in range(t.height_px) for col in range(t.width_px))
    return {'protocol': 'vsem.live-geometry.v1', 'live_view_id': capture['id'],
            'scan_operation_id': live['operation']['operation_id'], 'sweep_index': capture['sweep_index'],
            'offset_x_m': capture['offset_x_m'], 'offset_y_m': capture['offset_y_m'],
            'center_x_m': s.x_m+capture['offset_x_m'], 'center_y_m': s.y_m+capture['offset_y_m'],
            'pixel_size_m': pixel, 'field_width_m': capture['field'], 'height_m': pixel*t.height_px,
            'completed_pixels': completed, 'source_generation': generation}
