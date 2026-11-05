"""Closed observable v2:captured stage segments,never hidden specimen truth.

The original public v1 remains unchanged. Raster/optics admission is still the
original qualified1..8um envelope until wider-world source gates pass.
"""
from .core_public_protocol import observable_state as original_state
from .core_public_protocol import image_observation as original_image
from .core_public_protocol import validate_command,make_input

PROTOCOL='vsem.core-human.v2'


def observable_state(kernel):
    value=original_state(kernel);value['protocol']=PROTOCOL
    if 'capabilities' in value:value['capabilities']['within_raster_stage']=True
    return value


def image_observation(metadata):
    if metadata.get('protocol')!='vsem.private.native-image-cut.v2':raise ValueError('wrong_interactive_native_protocol')
    value=original_image(metadata);value['protocol']='vsem.core-native-image.v2'
    for public,private in zip(value['parameter_segments'],metadata['applied_segments']):
        g=private['geometry']
        public['stage']={'x_m':g['stage_x_m'],'y_m':g['stage_y_m'],'z_m':g['stage_z_m'],
            'working_distance_m':.010-g['stage_z_m']}
    return value
