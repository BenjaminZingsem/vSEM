"""Closed experimental wider-survey projection;not human-release enabled.

Only captured settings/geometry are observable. Private world/material codes,
probe/source coefficients,seeds and future physical states remain absent.
Original public v1/v2 admission stays unchanged in its original namespaces.
"""
from engine import human_episode_types as t
from .interactive_public_protocol import observable_state as previous_state,image_observation,make_input
from .core_public_protocol import validate_command as previous_validate,exact_keys

PROTOCOL='vsem.core-human.v3'


def observable_state(kernel):
    value=previous_state(kernel);value['protocol']=PROTOCOL
    if 'capabilities' in value:
        value['capabilities']['field_width_m']=[1e-7,.005]
        value['capabilities']['specimen_response']='ideal_grounded_reference'
    return value


def validate_command(value):
    exact_keys(value,('action','parameters','expected_stop_generation'))
    if value['action'] not in ('scan_live','scan_single','configure_live'):return previous_validate(value)
    action,p=value['action'],value['parameters'];t.integer(value['expected_stop_generation'])
    exact_keys(p,('width_px','height_px','field_width_m','offset_x_m','offset_y_m','dwell_ns'))
    if (type(p['width_px']) is not int or p['width_px'] not in (64,128,256,512,1024) or
            type(p['height_px']) is not int or p['height_px']!=p['width_px']):raise ValueError('supported_raster')
    t.real(p['field_width_m'],1e-7,.005)
    if type(p['dwell_ns']) is not int or p['dwell_ns'] not in (20000,100000,1000000):raise ValueError('supported_dwell')
    t.ScanRequest(**p)
    return {'action':action,'parameters':dict(p),'expected_stop_generation':value['expected_stop_generation']}
