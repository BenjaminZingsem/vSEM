"""New private Poisson process,conditional uniform photons in fixed mean windows.

For each intensity window,N~Poisson(W);conditional photon positions are iid
Uniform(0,W). This produces Poisson prefixes and independent increments. Closed
keys keep observer/query order irrelevant. This is a NEW count protocol;the old
qualified dyadic CountProcess remains immutable and is the full1024 baseline.
"""
from dataclasses import dataclass,field
import hashlib
import math
import re
import struct
import numpy as np

PROTOCOL='vsem.human-photon-uniform-window-prefix.v1'
WINDOW_MEAN=4096
MAX_MEAN=2**30

@dataclass(frozen=True)
class CountProcess:
    seed:bytes=field(repr=False)
    capture_id:str
    pixel_index:int
    channel:str
    _roots:dict=field(default_factory=dict,init=False,repr=False,compare=False)
    _positions:dict=field(default_factory=dict,init=False,repr=False,compare=False)

    def __post_init__(self):
        if type(self.seed) is not bytes or len(self.seed)!=32:
            raise ValueError('Private exact32-byte count seed required')
        if (type(self.capture_id) is not str or not 1<=len(self.capture_id)<=128 or
                re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]*',self.capture_id) is None):
            raise ValueError('Closed actual causal capture identity required')
        if type(self.pixel_index) is not int or not 0<=self.pixel_index<16777216:
            raise ValueError('Exact native pixel index required')
        if type(self.channel) is not str or self.channel not in ('SE','BSE'):
            raise ValueError('Exact detector channel required')
        if np.__version__!='1.26.4':raise RuntimeError('Qualified NumPy pin differs')

    def _rng(self,window,domain):
        key=(PROTOCOL.encode()+b'\0'+self.seed+b'\0'+self.capture_id.encode('ascii')+b'\0'+
             struct.pack('<I',self.pixel_index)+self.channel.encode()+struct.pack('<Q',window)+domain)
        seed=int.from_bytes(hashlib.sha256(key).digest(),'little')
        return np.random.Generator(np.random.PCG64(seed))

    def _root(self,window):
        if window not in self._roots:
            self._roots[window]=int(self._rng(window,b'COUNT').poisson(WINDOW_MEAN))
        return self._roots[window]

    def count(self,mean):
        if type(mean) not in (int,float) or not math.isfinite(mean) or not 0<=mean<=MAX_MEAN:
            raise ValueError('Finite closed Poisson intensity required')
        if mean==0:return 0
        full=int(mean//WINDOW_MEAN);fraction=float(mean-full*WINDOW_MEAN)
        total=sum(self._root(window) for window in range(full))
        if fraction:
            if full not in self._positions:
                positions=self._rng(full,b'POSITIONS').random(self._root(full),dtype=np.float64)
                positions.setflags(write=False);self._positions[full]=positions
            total+=int(np.count_nonzero(self._positions[full]<fraction/WINDOW_MEAN))
        if not 0<=total<2**32:raise OverflowError('Detector count outside native uint32 representation')
        return total
