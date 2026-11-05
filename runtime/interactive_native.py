"""Private v2 native image cuts with immutable initial and per-segment pose.

No expected rates,private world fields,seed or scenario answers are published.
The runtime must explicitly select the corresponding public projection.
"""
from dataclasses import asdict
import hashlib
import json
from engine.episode_raster import AppliedSegment
from .human_live_records import NativeImageReady


def publish_native(directory,capture,ledger):
    image_id='image-'+str(ledger.last)
    folder=directory/image_id;folder.mkdir()
    se,bse=capture.counts.read(0,capture.plan.pixel_count)
    for channel,raw in (('SE',se),('BSE',bse)):(folder/(channel+'.uint32')).write_bytes(raw)
    segments=list(capture.segments)
    if capture.elapsed>capture.segment_start:
        segments.append(AppliedSegment(capture.segment_start,capture.elapsed,capture.settings.current_pA,capture.label))
    application=[{**asdict(s),'settings':asdict(capture.labels[s.setting_id].settings),
        'geometry':asdict(capture.labels[s.setting_id].geometry)} for s in segments]
    holds=[asdict(hold) for hold in capture.holds]
    if capture.hold is not None and capture.elapsed>capture.hold:
        holds.append({'start_elapsed_ns':capture.hold,'end_elapsed_ns':capture.elapsed,
            'nominal_cursor_ns':capture.hold_cursor,'status':'OPEN','reason':'response_preparing_or_motion'})
    metadata={'protocol':'vsem.private.native-image-cut.v2','image_id':image_id,
        'causal_raster_id':capture.identity,'mode':capture.mode,'live_view_id':capture.view,
        'operation_id':capture.op,'numerical_ordinal':ledger.last,'physical_sequence':ledger.physical,
        'origin_ns':capture.origin,'elapsed_ns':capture.elapsed,'nominal_ns':capture.nominal,
        'configuration':asdict(capture.initial_configuration),'current_configuration':asdict(capture.config),
        'settings':asdict(capture.settings),'applied_segments':application,'blank_holds':holds,
        'incident_pA_ns':capture.total,'outcome':capture.outcome,'terminal_reason':capture.reason,
        'calibration_status':'generic_uncalibrated',
        'counts_sha256':{'SE':hashlib.sha256(se).hexdigest(),'BSE':hashlib.sha256(bse).hexdigest()}}
    raw=(json.dumps(metadata,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    (folder/'metadata.json').write_bytes(raw)
    return NativeImageReady(image_id,capture.identity,ledger.last,ledger.physical,hashlib.sha256(raw).hexdigest())
