"""Read/verify/upload an existing finite asset;no generator or seed is imported.

Only this private numerical graph owns the frozen GPU snapshot. Data remain
unavailable until every complete file stream validates. Missing/corrupt assets
fail closed;there is no regeneration,extension,device or provider fallback.
"""
import hashlib
import json
import os
from pathlib import Path
import time
import numpy as np
import torch
from .finite_catalog_format import load_header,array_chunks
from .hierarchical_specimen import PITCHES,HEIGHTS,CONTRAST,REGION_PITCH

GPU_UUID = os.environ.get('VSEM_GPU_UUID', 'UNCONFIGURED')


class GpuFiniteCatalog:
    def __init__(self,directory,manifest_sha256):
        self.validated=False;self.data=self.metadata=self.parameters=self.anchor=None
        if torch.__version__!='2.3.1+cu121' or np.__version__!='1.26.4':raise ValueError('pinned numerical packages required')
        if os.environ.get('CUDA_VISIBLE_DEVICES')!=GPU_UUID or torch.cuda.device_count()!=1:
            raise ValueError('exclusively leased physical GPU1 required')
        start=time.perf_counter();header=load_header(directory,manifest_sha256)
        if any(abs(v)>.05 for v in header.bounds_m):raise ValueError('finite material must fit the primary-CDF specimen envelope')
        for level,pitch,height,contrast in zip(header.levels,PITCHES,HEIGHTS,CONTRAST):
            if (level.pitch_m,level.height_m,level.contrast)!=(pitch,height,contrast):
                raise ValueError('exact frozen physical hierarchy required')
        if header.region_pitch_m!=REGION_PITCH:raise ValueError('exact frozen material-region scale required')
        # Small structural/coverage checks precede any large GPU allocation.
        region_raw=b''.join(array_chunks(header,header.regions))
        regions=np.frombuffer(region_raw,dtype=np.uint8).reshape(header.regions.shape)
        if np.any(regions>2):raise ValueError('three existing material-code axes required')
        x=(np.arange(regions.shape[2])+header.region_origin[0]+.5)*header.region_pitch_m
        y=(np.arange(regions.shape[1])+header.region_origin[1]+.5)*header.region_pitch_m
        xx,yy=np.meshgrid(x,y);a,b,c,d=header.bounds_m
        inside=(xx>a)&(xx<b)&(yy>c)&(yy<d)
        inventory=set(zip(*(plane[inside].tolist() for plane in regions)))
        if inventory!={(i,j,k) for i in range(3) for j in range(3) for k in range(3)}:
            raise ValueError('existing finite specimen lacks a complete27-combination inventory')
        anchor_raw=b''.join(array_chunks(header,header.anchor))
        anchor=np.frombuffer(anchor_raw,dtype='<f8').reshape(header.anchor.shape)
        if (not np.isfinite(anchor).all() or np.any(anchor[:,2:4]<=0) or
            np.any(anchor[:,8]<=0) or np.any(anchor[:,10]<=0) or not np.isin(anchor[:,7],[0.,1.,2.,3.]).all()):
            raise ValueError('valid frozen finite-feature coefficients required')
        elements=sum(level.table.byte_count//4 for level in header.levels)
        free,total=torch.cuda.mem_get_info();required=elements*4+anchor.nbytes+6*5*8+6*3*8
        if required>=free:raise MemoryError('actual available GPU1 cannot hold this frozen catalogue')
        data=torch.empty(elements,dtype=torch.int32,device='cuda:0');metadata=[];parameters=[];offset=0
        try:
            for level in header.levels:
                metadata.append((*level.origin,level.table.shape[2],level.table.shape[1],offset))
                parameters.append((level.pitch_m,level.height_m,level.contrast));position=offset
                for raw in array_chunks(header,level.table):
                    # This copies exactly the bytes whose stream is being hashed.
                    # No later file read can alter this GPU snapshot.
                    host=np.frombuffer(raw,dtype='<i4').copy()
                    if np.any(host<0) or np.any(host>=2147483647):raise ValueError('bounded stored counter values required')
                    count=len(host);data[position:position+count].copy_(torch.from_numpy(host))
                    position+=count
                if position-offset!=level.table.byte_count//4:raise ValueError('incomplete stored coefficient plane')
                offset=position
            if offset!=elements:raise ValueError('incomplete stored hierarchy')
            self.metadata=torch.tensor(metadata,dtype=torch.int64,device='cuda:0')
            self.parameters=torch.tensor(parameters,dtype=torch.float64,device='cuda:0')
            self.anchor=torch.tensor(anchor.copy(),dtype=torch.float64,device='cuda:0')
            torch.cuda.synchronize()
        except BaseException:
            del data;self.metadata=self.parameters=self.anchor=None
            raise
        self.header=header;self.data=data;self.regions=regions;self.inventory=tuple(sorted(inventory))
        self.loaded_bytes=required;self.load_s=time.perf_counter()-start;self.total_GPU_bytes=total
        self.source_identity=hashlib.sha256(json.dumps({'protocol':'vsem.private.frozen-GPU-catalog.v1',
            'manifest_sha256':header.manifest_sha256,'loader_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'metadata_i64':metadata,'no_counter_generation':True,'material_codes_activate_feedback':False},
            sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.validated=True

    def close(self):
        self.validated=False;self.data=self.metadata=self.parameters=self.anchor=None
