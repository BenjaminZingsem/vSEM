"""Private deterministic Poisson prefixes; no actor/dose/legacy RNG changes."""
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import math
import re
import numpy as np

PROTOCOL='vsem.detector-count-prefix.v1'
WINDOW_MEAN=2**30
NUMPY_VERSION='1.26.4'
_ID=re.compile(r'[A-Za-z0-9._:-]{1,128}\Z')


@dataclass(frozen=True)
class CountProcess:
    seed: bytes = field(repr=False)
    frame_id: str
    pixel_index: int
    channel: str
    protocol: str = field(default=PROTOCOL,init=False)

    def __post_init__(self):
        if np.__version__!=NUMPY_VERSION:
            raise ValueError('unqualified detector count runtime')
        if type(self.seed) is not bytes or len(self.seed)!=32:
            raise ValueError('exact private32-byte seed required')
        if type(self.frame_id) is not str or _ID.fullmatch(self.frame_id) is None:
            raise ValueError('safe exact frame identity required')
        if type(self.pixel_index) is not int or not 0<=self.pixel_index<=65535:
            raise ValueError('exact bounded pixel index required')
        if type(self.channel) is not str or self.channel not in ('SE','BSE'):
            raise ValueError('exact detector channel required')

    def _generator(self,depth,path):
        identity=json.dumps([PROTOCOL,self.frame_id,self.pixel_index,self.channel,depth,path],
            ensure_ascii=True,separators=(',',':')).encode('ascii')
        key=int.from_bytes(hmac.new(self.seed,identity,hashlib.sha256).digest(),'little')
        return np.random.Generator(np.random.PCG64(np.random.SeedSequence(key)))

    def count(self,expected_mean):
        if type(expected_mean) not in (int,float):
            raise ValueError('finite builtin expected mean required')
        try:
            valid=0<=expected_mean<=WINDOW_MEAN and math.isfinite(expected_mean)
        except (OverflowError,ValueError):valid=False
        if not valid:raise ValueError('expected mean outside count process window')
        mean=float(expected_mean)
        if mean==0.:return 0
        remaining=int(self._generator(-1,0).poisson(WINDOW_MEAN))
        if remaining<0 or remaining>2**32-1:
            raise ValueError('detector count overflow')
        if mean==WINDOW_MEAN:return remaining
        numerator,denominator=mean.as_integer_ratio()
        divisor=denominator*WINDOW_MEAN
        # divisor is a power of two. Binary integer paths preserve subnormals
        # without mean/W float underflow or rounded tree endpoints.
        bits=divisor.bit_length()-1
        total=path=0
        for depth in range(bits):
            if remaining==0:break
            left=int(self._generator(depth,path).binomial(remaining,.5))
            if not 0<=left<=remaining:raise ValueError('invalid detector split')
            rightward=(numerator>>(bits-depth-1))&1
            if rightward:total+=left;remaining-=left
            else:remaining=left
            path=path*2+rightward
        return total
