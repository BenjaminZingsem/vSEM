"""Explicit core SEM observable projections and closed operator commands.

New public development protocol;does not relabel legacy schemas. No generic
dataclass/truth serialization,source rates,seeds,world fields or solver digests.
"""
import math
from engine import human_episode_types as t

PROTOCOL = 'vsem.core-human.v1'


def exact_keys(value,names):
    if type(value) is not dict or set(value) != set(names): raise ValueError('closed_keys')


def settings(value):
    return {'current_pA':value.current_pA,'focus_offset_m':value.focus_offset_m,
        'stigmator_x':value.stigmator_x,'stigmator_y':value.stigmator_y}


def configuration(value):
    if value is None:return None
    g = value.geometry
    return {'width_px':g.width_px,'height_px':g.height_px,'field_width_m':g.field_width_m,
        'pixel_pitch_m':g.pixel_size_m,'magnification':.1/g.field_width_m,'magnification_reference_width_m':.1,
        'stage_x_m':g.stage_x_m,'stage_y_m':g.stage_y_m,'stage_z_m':g.stage_z_m,
        'offset_x_m':g.offset_x_m,'offset_y_m':g.offset_y_m,'dwell_ns':value.dwell_ns}


def observable_state(kernel):
    cut = kernel.causal_cut
    if cut is None:return {'protocol':PROTOCOL,'availability':'INITIALIZING'}
    state = cut.state; capture = kernel.verifier.capture
    progress = None
    if capture is not None:
        config = capture['config']; g = config.geometry
        line = g.width_px*config.dwell_ns; cursor = max(0,capture['nominal']-20_000_000)
        row,offset = divmod(cursor,line+100_000)
        completed = min(g.pixel_count,row*g.width_px+min(g.width_px,offset//config.dwell_ns))
        progress = {'completed_pixels':completed,'total_pixels':g.pixel_count,
            'elapsed_ns':capture['elapsed'],'nominal_ns':capture['nominal'],'source_id':capture['id']}
    return {'protocol':PROTOCOL,'availability':'AVAILABLE' if kernel.causal_error is None else 'QUARANTINED',
        'clock_mode':'realtime','retention':'buffered_development_not_crash_durable','calibration_status':'generic_uncalibrated',
        'observed_at_ns':cut.observed_at_ns,'delivery_age_ns':max(0,kernel.elapsed_ns()-cut.observed_at_ns),
        'causal_verified_ordinal':cut.last_ordinal,'numerical_verified_ordinal':kernel._last_num_ordinal,
        'phase':state.phase,'beam_blank':state.beam_blank,'interlock_reason':state.interlock_reason,
        'stage':{'x_m':state.stage_x_m,'y_m':state.stage_y_m,'z_m':state.stage_z_m,
            'working_distance_m':.010-state.stage_z_m,'z_supported_m':[-20e-6,20e-6]},
        'applied':settings(state.settings),'requested':settings(state.requested_settings) if state.requested_settings else None,
        'current_scan':configuration(state.current_configuration),'requested_scan':configuration(state.requested_configuration),
        'stop_generation':state.stop_generation,'live_source_id':state.live_view_id,'progress':progress,
        'episode_incident_pA_ns':state.episode_incident_pA_ns,
        'control':{'holder':state.lease.authority.holder_id,'epoch':state.lease.authority.epoch,
            'expires_ns':state.lease.expires_ns} if state.lease else None,
        'capabilities':{'stage_xyz':True,'focus':True,'stigmator':True,'physical_zoom':True,'live_roi':True,
            'native1024':True,'detectors':['SE'],'field_width_m':[1e-6,8e-6]}}


def image_observation(metadata):
    g = metadata['configuration']['geometry']; dwell = metadata['configuration']['dwell_ns']
    w,h = g['width_px'],g['height_px']; cursor = max(0,metadata['nominal_ns']-20_000_000)
    line = w*dwell; row,offset = divmod(cursor,line+100_000)
    completed = min(w*h,row*w+min(w,offset//dwell))
    active_ns = offset%dwell if completed < w*h and offset < line else 0
    segments = []
    for segment in metadata['applied_segments']:
        s = segment['settings']
        segments.append({'start_elapsed_ns':segment['start_elapsed_ns'],'end_elapsed_ns':segment['end_elapsed_ns'],
            'current_pA':s['current_pA'],'focus_offset_m':s['focus_offset_m'],'stigmator_x':s['stigmator_x'],'stigmator_y':s['stigmator_y']})
    return {'protocol':'vsem.core-native-image.v1','image_id':metadata['image_id'],
        'source_id':metadata['live_view_id'] or metadata['causal_raster_id'],'mode':metadata['mode'],
        'outcome':metadata['outcome'],'terminal_reason':metadata['terminal_reason'],
        'origin_ns':metadata['origin_ns'],'cut_elapsed_ns':metadata['elapsed_ns'],
        'numerical_verified_ordinal':metadata['numerical_ordinal'],'causal_verified_ordinal':metadata['numerical_ordinal'],
        'width_px':w,'height_px':h,'completed_pixels':completed,'active_dwell_ns':active_ns,'dwell_ns':dwell,
        'field_width_m':g['field_width_m'],'pixel_pitch_m':g['field_width_m']/w,
        'magnification':.1/g['field_width_m'],'magnification_reference_width_m':.1,
        'stage':{'x_m':g['stage_x_m'],'y_m':g['stage_y_m'],'z_m':g['stage_z_m'],'working_distance_m':.010-g['stage_z_m']},
        'offset_x_m':g['offset_x_m'],'offset_y_m':g['offset_y_m'],
        'incident_pA_ns':metadata['incident_pA_ns'],'parameter_segments':segments,
        'blank_holds':[{'start_elapsed_ns':item['start_elapsed_ns'],'end_elapsed_ns':item['end_elapsed_ns']} for item in metadata['blank_holds']],
        'raw_format':'uint32_little_endian','calibration_status':'generic_uncalibrated','detector':'SE'}


def validate_command(value):
    exact_keys(value,('action','parameters','expected_stop_generation'))
    action,parameters = value['action'],value['parameters']; t.integer(value['expected_stop_generation'])
    if action in ('scan_live','scan_single','configure_live'):
        exact_keys(parameters,('width_px','height_px','field_width_m','offset_x_m','offset_y_m','dwell_ns'))
        if parameters['width_px'] not in (64,128,256,512,1024) or type(parameters['width_px']) is not int or parameters['height_px'] != parameters['width_px'] or type(parameters['height_px']) is not int:raise ValueError('supported_raster')
        t.real(parameters['field_width_m'],1e-6,8e-6)
        if type(parameters['dwell_ns']) is not int or parameters['dwell_ns'] not in (20000,100000,1000000):raise ValueError('supported_dwell')
        t.ScanRequest(**parameters)
    elif action == 'optics':
        exact_keys(parameters,('current_pA','focus_offset_m','stigmator_x','stigmator_y')); t.EpisodeSettings(**parameters)
    elif action == 'stage_move':
        exact_keys(parameters,('x_m','y_m','z_m'))
        for key,low,high in (('x_m',-.025,.025),('y_m',-.025,.025),('z_m',-20e-6,20e-6)):t.real(parameters[key],low,high)
    elif action == 'stop':exact_keys(parameters,())
    elif action == 'freeze':exact_keys(parameters,('source_id',)); t.identity(parameters['source_id'])
    else:raise ValueError('unsupported_action')
    return {'action':action,'parameters':dict(parameters),'expected_stop_generation':value['expected_stop_generation']}


def make_input(command,operation_id,authority):
    action,p,generation = command['action'],command['parameters'],command['expected_stop_generation']
    if action == 'stop':return t.EpisodeInputs(stop=t.SafetyStop(operation_id,authority))
    if action == 'optics':normal = t.SetOptics(operation_id,authority,t.EpisodeSettings(**p))
    elif action == 'stage_move':normal = t.MoveStageXYZ(operation_id,authority,p['x_m'],p['y_m'],p['z_m'],generation)
    elif action == 'configure_live':normal = t.ConfigureLive(operation_id,authority,t.ScanRequest(**p),generation)
    elif action == 'freeze':normal = t.FreezeLive(operation_id,authority,p['source_id'],generation)
    else:normal = t.StartCapture(operation_id,authority,'LIVE' if action == 'scan_live' else 'SINGLE',t.ScanRequest(**p),generation)
    return t.EpisodeInputs(normal=normal)
