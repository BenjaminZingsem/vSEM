"""Pure request validation, independent of the external fibsemOS package."""
from .protocol import keys, raster, real, stage
from .units import current_to_pa, pa_to_current

FRAME = 'vsem_specimen_xyz_m'
IMAGE_FIELDS = (
    'resolution', 'dwell_time', 'hfw', 'autocontrast', 'beam_type', 'save',
    'filename', 'path', 'reduced_area', 'line_integration', 'scan_interlacing',
    'frame_integration', 'drift_correction', 'bit_depth')


def image_request(value):
    """Validate the complete normalized ImageSettings before any side effect.

    Upstream defaults (1536x1024, 1us) are intentionally not silently adapted.
    Raw persistence is explicit; upstream image saving has no qualified companion
    contract yet. Reduced-area geometry and processing need separate mappings.
    """
    keys(value, IMAGE_FIELDS)
    if value['beam_type'] != 'ELECTRON':
        raise ValueError('only the electron beam is supported')
    for name in ('autocontrast', 'drift_correction', 'save'):
        if value[name] is not False:
            raise ValueError('unsupported acquisition processing or save request')
    for name in ('path', 'reduced_area', 'line_integration', 'scan_interlacing',
                 'frame_integration', 'bit_depth'):
        if value[name] is not None:
            raise ValueError('unsupported acquisition option')
    if type(value['filename']) is not str or not 1 <= len(value['filename']) <= 128:
        raise ValueError('invalid inactive filename label')
    shape = value['resolution']
    if type(shape) not in (list, tuple) or len(shape) != 2:
        raise ValueError('explicit square resolution required')
    result = {'width_px': shape[0], 'height_px': shape[1],
              'hfw_m': value['hfw'], 'dwell_s': value['dwell_time']}
    raster(result)
    return result


def beam_write(name, value):
    """Validate before upstream coercion, clipping or nearest-choice snapping."""
    if name == 'current':
        return pa_to_current(current_to_pa(value))
    if name == 'stigmation':
        keys(value, ('x', 'y'))
        return {'x': real(value['x'], -1., 1.), 'y': real(value['y'], -1., 1.)}
    raise ValueError('unsupported or read-only beam parameter')


def stage_position(value):
    keys(value, ('x', 'y', 'z', 'r', 't', 'coordinate_system', 'name'))
    if value['r'] is not None or value['t'] is not None:
        raise ValueError('rotation and tilt are unsupported, including explicit zero')
    if value['name'] is not None and type(value['name']) is not str:
        raise ValueError('invalid position label')
    result = {'x_m': value['x'], 'y_m': value['y'], 'z_m': value['z'],
              'frame': value['coordinate_system']}
    stage(result)
    return result
