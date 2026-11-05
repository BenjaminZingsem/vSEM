"""Actual off-owner image/count processing and immutable native partial cuts."""
from collections import deque
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import time

from engine import human_episode_types as t
from engine.human_episode_facts import EpisodeFact
from .human_realtime_records import NumericalCut
from .human_live_records import NativeImageReady


def publish_native(directory, capture, ledger):
    """Original native counts and explicit captured metadata,no expected rates."""
    image_id = 'image-'+str(ledger.last)
    folder = directory/image_id; folder.mkdir()
    se, bse = capture.counts.read(0, capture.plan.pixel_count)
    for channel, raw in (('SE',se),('BSE',bse)):
        (folder/(channel+'.uint32')).write_bytes(raw)
    segments = list(capture.segments)
    if capture.elapsed > capture.segment_start:
        from engine.episode_raster import AppliedSegment
        segments.append(AppliedSegment(capture.segment_start,capture.elapsed,capture.settings.current_pA,capture.label))
    application = [{**asdict(segment),'settings':asdict(capture.labels[segment.setting_id].settings)} for segment in segments]
    holds = [asdict(hold) for hold in capture.holds]
    if capture.hold is not None and capture.elapsed > capture.hold:
        holds.append({'start_elapsed_ns':capture.hold,'end_elapsed_ns':capture.elapsed,
            'nominal_cursor_ns':capture.hold_cursor,'status':'OPEN','reason':'response_preparing'})
    metadata = {'protocol':'vsem.private.native-image-cut.v1','image_id':image_id,
        'causal_raster_id':capture.identity,'mode':capture.mode,'live_view_id':capture.view,
        'operation_id':capture.op,'numerical_ordinal':ledger.last,'physical_sequence':ledger.physical,
        'origin_ns':capture.origin,'elapsed_ns':capture.elapsed,'nominal_ns':capture.nominal,
        'configuration':asdict(capture.config),'settings':asdict(capture.settings),
        'applied_segments':application,'blank_holds':holds,'incident_pA_ns':capture.total,
        'outcome':capture.outcome,'terminal_reason':capture.reason,'calibration_status':'generic_uncalibrated',
        'counts_sha256':{'SE':hashlib.sha256(se).hexdigest(),'BSE':hashlib.sha256(bse).hexdigest()}}
    raw = (json.dumps(metadata,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    (folder/'metadata.json').write_bytes(raw)
    return NativeImageReady(image_id,capture.identity,ledger.last,ledger.physical,hashlib.sha256(raw).hexdigest())


def numerical_worker(initial_settings,namespace,nonce,links,seed,directory,delay_s,parent_pid,binding_allowance,image_period_s):
    # Scientific imports/large arrays never enter the scalar physical process.
    from engine.human_cached_source import CachedResponseRegistry
    from engine.human_specimen_map import NativeWorldMap
    from engine.human_alignment_specimen import HumanAlignmentSpecimen
    from engine.human_live_image_ledger import EpisodeExposureLedger
    from .human_live_kernel import Wire
    registry = CachedResponseRegistry(world=NativeWorldMap(specimen=HumanAlignmentSpecimen(),spacing_m=1.25e-9),
        binding_capacity=binding_allowance)
    startup,jobs,facts,banks,cuts,images = (Wire(link,nonce) for link in links)
    if not startup.put(registry.science): raise RuntimeError('Science startup lane unavailable')
    ledger = EpisodeExposureLedger(registry.science,initial_settings,episode_namespace=namespace,
        seed=seed,bank_resolver=registry.resolve)
    directory = Path(directory)
    pending_banks,pending_cuts,pending_images = deque(),deque(),deque()
    last_image_time = {}
    while True:
        if os.getppid() != parent_pid: return
        for pending,wire in ((pending_banks,banks),(pending_cuts,cuts),(pending_images,images)):
            if pending and wire.put(pending[0]): pending.popleft()
        item = jobs.get()
        if item is not None:
            ticket = t.exact(item[0],t.BankTicket)
            try: result = registry.prepare(ticket)
            except Exception: result = t.BankFailed(ticket)
            pending_banks.append(result)
        item = facts.get()
        if item is None:
            time.sleep(.001); continue
        fact = t.exact(item[0],EpisodeFact)
        if delay_s: time.sleep(delay_s)
        receipt = ledger.ingest((fact,))
        if receipt.status != 'COMMITTED': raise RuntimeError('Actual live numerical trace rejected: '+receipt.reason)
        raster = None
        if fact.kind in ('RASTER_START','PREFIX','HOLD_START','HOLD_END','RASTER_END'): raster = fact.body[0]
        elif fact.kind == 'SETTINGS_APPLIED': raster = fact.body[5]
        if raster is None:
            pending_cuts.append(NumericalCut(ledger.last,ledger.physical,ledger.total)); continue
        capture = ledger.captures[raster]; g = capture.config.geometry
        se_hash = bse_hash = None
        now = time.perf_counter()
        if fact.kind == 'RASTER_END' or now-last_image_time.get(raster,now) >= image_period_s:
            image = publish_native(directory,capture,ledger)
            pending_images.append(image); last_image_time[raster] = now
            if fact.kind == 'RASTER_END':
                metadata = json.loads((directory/image.image_id/'metadata.json').read_bytes())
                se_hash,bse_hash = metadata['counts_sha256']['SE'],metadata['counts_sha256']['BSE']
        elif raster not in last_image_time: last_image_time[raster] = now
        pending_cuts.append(NumericalCut(ledger.last,ledger.physical,ledger.total,raster,capture.outcome,
            g.width_px,g.height_px,capture.total,se_hash,bse_hash))
