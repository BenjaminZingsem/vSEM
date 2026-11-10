"""Explicit no-growth finite source;original off-owner count/publication loop."""
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


from .interactive_native import publish_native
from .preparation_diagnostics import PreparationDiagnostics


def _numerical_worker(initial_settings,namespace,nonce,links,seed,directory,delay_s,parent_pid,binding_allowance,image_period_s,finite_catalogue):
    # Scientific imports/large arrays never enter the scalar physical process.
    from engine.finite_source import FiniteResponseRegistry
    from engine.finite_image_ledger import EpisodeExposureLedger
    from .hierarchical_human_kernel import Wire
    # New private wider-world source;still explicitly ideal grounded.
    from .finite_launch_spec import FrozenFiniteLaunch
    t.exact(finite_catalogue,FrozenFiniteLaunch);finite_catalogue.__post_init__()
    registry=FiniteResponseRegistry(catalogue_directory=finite_catalogue.directory,
        manifest_sha256=finite_catalogue.manifest_sha256,binding_capacity=binding_allowance)
    registry.prepare = PreparationDiagnostics(directory).guard(registry.prepare)
    startup,jobs,facts,banks,cuts,images = (Wire(link,nonce) for link in links)
    if not startup.put(registry.science): raise RuntimeError('Science startup lane unavailable')
    ledger = EpisodeExposureLedger(registry.science,initial_settings,episode_namespace=namespace,
        seed=seed,bank_resolver=registry.resolve,bounds_m=registry.bounds_m,cell_size_m=registry.cell_size_m)
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


def numerical_worker(*args):
    from .prepared_resources import PreparedGpuLease
    with PreparedGpuLease(Path(__file__).resolve().parents[1]) as lease:
        lease.admit_device()
        os.environ['TRITON_CACHE_DIR']=str(Path(__file__).resolve().parents[1]/'.bootstrap-tmp/finite-triton-cache')
        return _numerical_worker(*args)
