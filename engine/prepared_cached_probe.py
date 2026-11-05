"""Separately identified exact CPU preparation over a pinned native map.

Only source-grid assembly changes; the qualified positive Gaussian, height layers,
convolution and acquisition sampling remain the inherited reference equations.
"""
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
import time
import numpy as np
from .human_cached_probe import CachedProbeBuilder, _Scene
from .human_specimen_map import available_memory_bytes, digest, canonical
from .human_mapped_probe import emitted_and_collected
from .prepared_specimen_map import PreparedWorldMap


class PreparedProbeBuilder(CachedProbeBuilder):
    def __init__(self, world, *, cache_bytes=None):
        if type(world) is not PreparedWorldMap:
            raise ValueError('Exact prepared native-world map required')
        self.world = world
        budget = available_memory_bytes() // 2 if cache_bytes is None else cache_bytes
        if type(budget) is not int or budget < 1:
            raise ValueError('Positive trusted/measured spectrum allowance required')
        self.budget = budget
        self.resident = 0
        self.scenes = OrderedDict()
        self.scene_builds = self.scene_hits = 0
        self.source_pin = digest(Path(__file__).read_bytes())

    def _scene(self, key):
        if key in self.scenes:
            scene = self.scenes.pop(key)
            self.scenes[key] = scene
            self.scene_hits += 1
            return scene
        xmin, ymin, nx, ny = key
        if nx * ny * 256 > available_memory_bytes() * 4 // 5:
            raise MemoryError('Current available memory cannot admit native source extent')
        spacing = self.world.spacing
        fields = self.world.surface_grid(np.arange(xmin, xmin+nx)*spacing,
                                         np.arange(ymin, ymin+ny)*spacing)
        emitted, collected = emitted_and_collected(fields)
        if np.any(emitted > 4) or np.any(collected < 0):
            raise ValueError('Source emission envelope exceeded')
        spectra = tuple(np.fft.rfftn(value) for value in (emitted, collected))
        for spectrum in spectra:
            spectrum.setflags(write=False)
        size = sum(s.nbytes for s in spectra)
        scene = _Scene(xmin, ymin, nx, ny, spectra, size)
        self.scene_builds += 1
        if size <= self.budget:
            while self.resident + size > self.budget:
                _, old = self.scenes.popitem(last=False)
                self.resident -= old.bytes
            self.scenes[key] = scene
            self.resident += size
        return scene

    def build(self, geometry, settings):
        if digest(Path(__file__).read_bytes()) != self.source_pin:
            raise ValueError('Prepared probe source changed')
        start = time.perf_counter()
        bank = super().build(geometry, settings)
        identity = digest(canonical({'prior_response': bank.source_identity,
            'prepared_probe_source': self.source_pin, 'variant': 'prepared-cartesian-cpu-v1'}))
        return replace(bank, source_identity=identity, construction_s=time.perf_counter()-start)
