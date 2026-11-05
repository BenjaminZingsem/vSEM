"""Private prepared GPU source with explicit immutable scientific provenance.

One expected response source for the original causal owner/numerical ledger.
This does not own time,authority,dose,noise or acquired images.
"""
import math
from pathlib import Path
import numpy as np
from .human_episode_types import ScienceIdentity, BankTicket, BankReady, ScalarBankHandle, exact, integer
from .human_mapped_response_source import MappedResponseRegistry, ResolvedMappedSource, source_identity, _digest
from .human_fast_mapped_source import fast_pins
from .human_live_mapped_source import projection_pin
from .human_specimen_map import digest
from .human_mapped_probe import HumanMappedProfile, SUPPORT_SIGMA
from .beam_profile import HEIGHT_BOUND_M
from .primary_fluence import CELL_SIZES_M
from .compact_world_extent import compact_axis_extent
from .prepared_specimen_map import PreparedWorldMap
from .prepared_gpu_probe import PreparedGPUProbeBuilder
from .human_photon_prefix import PROTOCOL
from .core_cached_source import MemoizedBuilder


def prepared_pins():
    folder = Path(__file__).resolve().parent
    return {'original_source': source_identity(), 'photon': fast_pins(),
            'grounded_projection': projection_pin(),
            'prepared': {n: digest((folder/n).read_bytes()) for n in (
                'prepared_response_source.py', 'prepared_specimen_map.py', 'prepared_gpu_probe.py',
                'compact_world_extent.py', 'multiscale_alignment_specimen.py', 'core_cached_source.py')},
            'tile_groups': digest((folder.parent/'packages/specimens/tile_groups.py').read_bytes())}


def initial_world_bounds(spacing):
    profile = HumanMappedProfile()
    base = profile.components(1e-9).sigma_base_m
    defocus = 25e-6+abs(profile._focus_reference_m)+HEIGHT_BOUND_M
    astig = profile.astigmatic_plane_scale_m*math.hypot(
        1+abs(profile._stig_reference_x), 1+abs(profile._stig_reference_y))
    sigma = math.sqrt(base*base+profile.semiangle_rad**2/4*(defocus+astig)**2)
    margin = math.ceil(SUPPORT_SIGMA*sigma/spacing)+2
    start, size = compact_axis_extent(math.floor(-4e-6/spacing)-margin,
                                       math.ceil(4e-6/spacing)+margin+1)
    return (start*spacing, start*spacing, (start+size-1)*spacing, (start+size-1)*spacing)


class PreparedResponseRegistry(MappedResponseRegistry):
    def __init__(self, *, world, cell_size_m=25e-9, generation=1, binding_capacity=4096):
        if type(world) is not PreparedWorldMap or type(cell_size_m) is not float or cell_size_m not in CELL_SIZES_M:
            raise ValueError('Exact prepared world and qualified primary grid required')
        integer(generation, 1)
        integer(binding_capacity, 1)
        self.world, self.cell_size_m = world, cell_size_m
        self.generation, self.capacity = generation, binding_capacity
        self.pins = prepared_pins()
        builder = PreparedGPUProbeBuilder(world)
        self.science = ScienceIdentity(HumanMappedProfile().profile_id, _digest(world.identity),
            _digest({'primary_cell_size_hex': cell_size_m.hex(), 'native_spacing_hex': world.spacing.hex(),
                     'frame': 'stage-xyz-raster-y-up-v1'}), 'VECTOR',
            _digest({'source': self.pins, 'torch': builder.torch.__version__, 'CUDA': builder.torch.version.cuda,
                     'precision': 'float64/complex128', 'variant': 'prepared-grounded-GPU1-v1'}), PROTOCOL)
        self.gpu_builder = builder
        self.builder = MemoizedBuilder(builder, self.science)
        self._bindings, self._tickets = {}, {}

    def prepare_initial(self):
        return self.world.prepare_bounds(*initial_world_bounds(self.world.spacing))

    def prepare(self, ticket):
        exact(ticket, BankTicket)
        if ticket.science != self.science or ticket.custodian_generation != self.generation or prepared_pins() != self.pins:
            raise ValueError('Foreign/changed prepared scientific source or generation')
        previous = self._tickets.get(ticket.job_id)
        if previous is not None:
            if previous[0] != ticket:
                raise ValueError('Owned prepared job identity rebound')
            return BankReady(ticket, previous[1])
        if len(self._bindings) >= self.capacity:
            raise ValueError('Trusted measured binding allowance exhausted')
        bank = self.builder.build(ticket.configuration.geometry, ticket.settings)
        descriptor = _digest({'bank': bank.source_identity, 'science': self.science.solver_source_digest,
                              'dwell_ns': ticket.configuration.dwell_ns})
        handle = ScalarBankHandle('prepared-'+str(len(self._bindings)+1), self.generation, descriptor,
            self.science.solver_source_digest, ticket.configuration.geometry, ticket.settings)
        self._bindings[handle.handle_id] = ResolvedMappedSource(handle, bank, self.cell_size_m)
        self._tickets[ticket.job_id] = (ticket, handle)
        return BankReady(ticket, handle)

    def close(self):
        self._bindings.clear()
        self._tickets.clear()
        self.builder.cache.clear()
        self.builder.resident = 0
        self.gpu_builder.close()
