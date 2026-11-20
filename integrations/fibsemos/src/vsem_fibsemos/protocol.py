"""Closed public command mappings. No engine or evaluator imports."""
import json
import math
import re

from .errors import ProtocolError
from .units import current_to_pa, dwell_to_ns, hfw, resolution


def real(value, low, high):
    if type(value) not in (int, float):
        raise ValueError("finite built-in number required")
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise ValueError("finite bounded number required") from None
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError("number outside supported envelope")
    return result


def integer(value, low=0, high=2**63 - 1):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("bounded integer required")
    return value


def identity(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise ValueError("invalid observable identifier")
    return value


def keys(value, required, optional=()):
    if type(value) is not dict or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ValueError("unsupported or missing fields")


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate field")
            result[key] = value
        return result

    def invalid(_):
        raise ValueError("non-finite JSON")

    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
        # JSON accepts overflowing finite literals such as 1e999; reject these too.
        json.dumps(result, allow_nan=False)
        return result
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ProtocolError("invalid bounded JSON response") from None


def raster(value):
    keys(value, ('width_px', 'height_px', 'hfw_m', 'dwell_s'), ('offset_x_m', 'offset_y_m'))
    width, height = resolution(value['width_px'], value['height_px'])
    return {'width_px': width, 'height_px': height,
            'field_width_m': hfw(value['hfw_m']), 'dwell_ns': dwell_to_ns(value['dwell_s']),
            'offset_x_m': real(value.get('offset_x_m', 0.), -.005, .005),
            'offset_y_m': real(value.get('offset_y_m', 0.), -.005, .005)}


def optics(value):
    keys(value, ('current_a', 'focus_offset_m', 'stigmator_x', 'stigmator_y'))
    return {'current_pA': current_to_pa(value['current_a']),
            'focus_offset_m': real(value['focus_offset_m'], -25e-6, 25e-6),
            'stigmator_x': real(value['stigmator_x'], -1., 1.),
            'stigmator_y': real(value['stigmator_y'], -1., 1.)}


def stage(value):
    keys(value, ('x_m', 'y_m', 'z_m', 'frame'))
    if value['frame'] != 'vsem_specimen_xyz_m':
        raise ValueError("undeclared coordinate transform")
    return {key: real(value[key], -limit, limit)
            for key, limit in (('x_m', .025), ('y_m', .025), ('z_m', 20e-6))}


def receipt(value, expected_id=None):
    try:
        keys(value, ('operation_id', 'status', 'reason', 'observed_at_ns'))
        identity(value['operation_id'])
        if expected_id is not None and value['operation_id'] != expected_id:
            raise ValueError("operation identity changed")
        if value['status'] not in ('RECEIVED', 'ACCEPTED', 'RUNNING', 'COMPLETED', 'REJECTED', 'CANCELLED', 'UNKNOWN'):
            raise ValueError("unknown disposition")
        if value['reason'] is not None and (type(value['reason']) is not str or len(value['reason']) > 256):
            raise ValueError("invalid reason")
        if value['observed_at_ns'] is not None:
            integer(value['observed_at_ns'])
        return dict(value)
    except (ValueError, TypeError):
        raise ProtocolError("invalid operation receipt") from None


def acquisitions(value, expected_id, expected_command=None):
    """Closed public v1 association; never search an image list or infer IDs."""
    relations = {'scan_single': ('started_single',), 'scan_live': ('live_session',),
                 'configure_live': ('configuration_applied', 'already_active'),
                 'freeze': ('freeze_of',)}
    try:
        identity(expected_id)
        keys(value, ('protocol', 'operation_id', 'command', 'receipt',
                     'association', 'latest_cut', 'final_cut'))
        if value['protocol'] != 'vsem.operation-acquisitions.v1' or value['operation_id'] != expected_id:
            raise ValueError('association protocol/operation mismatch')
        command = value['command']
        if command not in ('lease', 'scan_single', 'scan_live', 'configure_live',
                           'freeze', 'optics', 'stage_move', 'stop'):
            raise ValueError('unknown association command')
        if expected_command is not None and command != expected_command:
            raise ValueError('association command mismatch')
        observed_receipt = receipt(value['receipt'], expected_id)
        association = value['association']
        if association is not None:
            keys(association, ('relation', 'source_id', 'raster_id', 'applied_at_ns'))
            if association['relation'] not in relations.get(command, ()):
                raise ValueError('wrong acquisition relation')
            identity(association['source_id'])
            identity(association['raster_id'])
            integer(association['applied_at_ns'])
            if command == 'scan_single' and association['source_id'] != association['raster_id']:
                raise ValueError('single source is not its raster')
            association = dict(association)
        cuts = {}
        for name in ('latest_cut', 'final_cut'):
            cut = value[name]
            if cut is not None:
                keys(cut, ('image_id', 'source_id', 'raster_id', 'cut_elapsed_ns', 'outcome'))
                for field in ('image_id', 'source_id', 'raster_id'):
                    identity(cut[field])
                integer(cut['cut_elapsed_ns'])
                if cut['outcome'] not in ('ACQUIRING', 'COMPLETED', 'CANCELLED'):
                    raise ValueError('unknown cut outcome')
                if association is None or cut['source_id'] != association['source_id']:
                    raise ValueError('cut lacks the observed source association')
                if (name == 'final_cut' or command not in ('scan_live', 'freeze')) and cut['raster_id'] != association['raster_id']:
                    raise ValueError('cut differs from associated raster')
                if name == 'final_cut' and cut['outcome'] == 'ACQUIRING':
                    raise ValueError('partial cut is not final')
                cut = dict(cut)
            cuts[name] = cut
        return dict(protocol=value['protocol'], operation_id=expected_id, command=command,
                    receipt=observed_receipt, association=association, **cuts)
    except (KeyError, ValueError, TypeError):
        raise ProtocolError('invalid public acquisition association') from None
