"""Explicit GPU1-only float64 private probe variant; no implicit CPU fallback.

Caller must own the trusted exclusive GPU lease and pin its runtime. This module
never selects another GPU, handles credentials, launches a service or changes time.
Only intrinsic spectra are cached. Noise/exposure/images remain outside this code.
"""
from collections import OrderedDict
from pathlib import Path
import math
import os
import time
import numpy as np
from .human_specimen_map import available_memory_bytes, canonical, digest
from .prepared_specimen_map import PreparedWorldMap
from .human_episode_types import EpisodeGeometry, EpisodeSettings, exact
from .compact_world_extent import compact_axis_extent
from .human_mapped_probe import (HumanMappedProfile, MappedProbeBank, effective_settings,
    emitted_and_collected, _positive_kernel, HEIGHT_STEP_M, SUPPORT_SIGMA)
from .beam_profile import HEIGHT_BOUND_M

GPU_UUID = os.environ.get('VSEM_GPU_UUID', 'UNCONFIGURED')


class PreparedGPUProbeBuilder:
    def __init__(self, world):
        if type(world) is not PreparedWorldMap:
            raise ValueError('Exact prepared map required')
        if os.environ.get('CUDA_VISIBLE_DEVICES') != GPU_UUID:
            raise ValueError('Explicit qualified physical GPU1 visibility required before import')
        import torch
        if torch.__version__ != '2.3.1+cu121' or torch.version.cuda != '12.1':
            raise ValueError('Only the measured pinned torch/CUDA variant is admitted')
        if torch.cuda.device_count() != 1:
            raise ValueError('Exactly one explicit CUDA device required')
        self.torch, self.world = torch, world
        self.scenes = OrderedDict()
        self.resident = self.scene_builds = self.scene_hits = 0
        self.source_pin = digest(Path(__file__).read_bytes())
        self.timing = {}

    def _scene(self, key):
        torch = self.torch
        if key in self.scenes:
            scene = self.scenes.pop(key)
            self.scenes[key] = scene
            self.scene_hits += 1
            return scene
        xmin, ymin, nx, ny = key
        if nx*ny*128 > available_memory_bytes()*4//5:
            raise MemoryError('Actual host memory cannot admit private native GPU source')
        # Reserve source+FFT/workspace before construction; evict only own spectra.
        estimated_peak = nx*ny*160
        free, total = torch.cuda.mem_get_info()
        while estimated_peak > free*4//5 and self.scenes:
            _, previous = self.scenes.popitem(last=False)
            self.resident -= sum(v.numel()*v.element_size() for v in previous)
            del previous
            torch.cuda.empty_cache()
            free, total = torch.cuda.mem_get_info()
        if estimated_peak > free*4//5:
            raise MemoryError('Actual GPU1 memory cannot admit full private native extent')
        t0 = time.perf_counter()
        spacing = self.world.spacing
        fields = self.world.surface_grid(np.arange(xmin, xmin+nx)*spacing,
                                         np.arange(ymin, ymin+ny)*spacing)
        emitted, collected = emitted_and_collected(fields)
        if np.any(emitted > 4) or np.any(collected < 0):
            raise ValueError('Source emission envelope exceeded')
        self.timing['map_s'] = time.perf_counter()-t0
        t0 = time.perf_counter()
        with torch.no_grad():
            spectra = tuple(torch.fft.rfftn(torch.as_tensor(value, dtype=torch.float64, device='cuda:0'))
                            for value in (emitted, collected))
        torch.cuda.synchronize()
        self.timing['scene_fft_and_upload_s'] = time.perf_counter()-t0
        self.scene_builds += 1
        self.scenes[key] = spectra
        self.resident += sum(v.numel()*v.element_size() for v in spectra)
        return spectra

    def build(self, geometry, settings):
        exact(geometry, EpisodeGeometry)
        exact(settings, EpisodeSettings)
        if digest(Path(__file__).read_bytes()) != self.source_pin:
            raise ValueError('GPU probe source changed')
        torch, world = self.torch, self.world
        start = time.perf_counter()
        self.timing = {}
        spacing = world.spacing
        beam = effective_settings(settings, geometry)
        profile = HumanMappedProfile()
        px = geometry.center_x_m+(np.arange(geometry.width_px)+.5-geometry.width_px/2)*geometry.pixel_size_m
        py = geometry.center_y_m+(geometry.height_px/2-np.arange(geometry.height_px)-.5)*geometry.pixel_size_m
        x, y = np.meshgrid(px, py)
        heights = world.surface_arrays(x, y)[0].reshape(-1)
        lower = np.floor(heights/HEIGHT_STEP_M).astype(np.int64)
        fraction = heights/HEIGHT_STEP_M-lower
        first, last = int(lower.min()), int(lower.max())+1
        levels = [i*HEIGHT_STEP_M for i in range(first, last+1)]
        if any(abs(h) > HEIGHT_BOUND_M for h in levels):
            raise ValueError('Height interpolation outside optical envelope')
        covariances = [profile.covariance(beam, h) for h in levels]
        mx = max(math.ceil(SUPPORT_SIGMA*math.sqrt(c.xx_m2)/spacing) for c in covariances)+2
        my = max(math.ceil(SUPPORT_SIGMA*math.sqrt(c.yy_m2)/spacing) for c in covariances)+2
        xmin, nx = compact_axis_extent(math.floor(float(px.min())/spacing)-mx, math.ceil(float(px.max())/spacing)+mx+1)
        ymin, ny = compact_axis_extent(math.floor(float(py.min())/spacing)-my, math.ceil(float(py.max())/spacing)+my+1)
        spectra = self._scene((xmin, ymin, nx, ny))
        gx, gy = x.reshape(-1)/spacing-xmin, y.reshape(-1)/spacing-ymin
        ix, iy = np.floor(gx).astype(np.int64), np.floor(gy).astype(np.int64)
        fx, fy = gx-ix, gy-iy
        result = [np.zeros(geometry.pixel_count, dtype=np.float64) for _ in range(2)]
        used = 0
        t0 = time.perf_counter()
        with torch.no_grad():
            # Native-grid convolution remains full resolution, with the same
            # positive finite PSF. Only actual acquisition pixels are read back.
            for index, covariance in zip(range(first, last+1), covariances):
                weights = np.where(lower == index, 1-fraction, np.where(lower+1 == index, fraction, 0.))
                mask = weights != 0
                if not mask.any():
                    continue
                used += 1
                kernel, rx, ry = _positive_kernel(covariance, spacing)
                folded = np.zeros((ny, nx), dtype=np.float64)
                for row in range(kernel.shape[0]):
                    folded[(row-ry) % ny, (np.arange(kernel.shape[1])-rx) % nx] = kernel[row]
                transfer = torch.fft.rfftn(torch.as_tensor(folded, dtype=torch.float64, device='cuda:0'))
                a = torch.as_tensor(ix[mask], device='cuda:0')
                b = torch.as_tensor(iy[mask], device='cuda:0')
                u = torch.as_tensor(fx[mask], device='cuda:0')
                v = torch.as_tensor(fy[mask], device='cuda:0')
                for target, spectrum in zip(result, spectra):
                    plane = torch.fft.irfftn(spectrum*transfer, s=(ny, nx))
                    samples = ((1-u)*(1-v)*plane[b, a] + u*(1-v)*plane[b, a+1] +
                               (1-u)*v*plane[b+1, a] + u*v*plane[b+1, a+1])
                    target[mask] += samples.cpu().numpy()*weights[mask]
        torch.cuda.synchronize()
        self.timing['convolution_and_sampling_s'] = time.perf_counter()-t0
        folder = Path(__file__).resolve().parent
        pins = {name: digest((folder/name).read_bytes()) for name in ('beam_profile.py', 'human_mapped_probe.py',
                'compact_world_extent.py', 'prepared_gpu_probe.py')}
        identity = digest(canonical({'map': world.identity_digest, 'source': pins,
            'geometry': list(geometry._key()), 'settings': list(settings._key()),
            'native_extent': [xmin, ymin, nx, ny], 'height_step_hex': HEIGHT_STEP_M.hex(),
            'support_sigma': SUPPORT_SIGMA, 'variant': 'positive-native-GPU1-float64-v1',
            'torch': torch.__version__, 'CUDA': torch.version.cuda}))
        return MappedProbeBank(geometry, settings, identity, result[0], result[1], heights,
            time.perf_counter()-start, spacing, used)

    def close(self):
        self.scenes.clear()
        self.resident = 0
        self.torch.cuda.empty_cache()
