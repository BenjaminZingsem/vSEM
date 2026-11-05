"""Offline preparation only:serialize every finite feature before instrument use.

Uses the independently accepted, hash-pinned pure-integer helper. No instrument service,
operator route,beam exposure,network,model or automatic provider fallback.
Partial output is preserved on failure and never admitted as a finished pack.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while True:
            data=stream.read(8*1024*1024)
            if not data:break
            digest.update(data)
    return digest.hexdigest()


def entry(path,dtype,shape):return {'file':path.name,'dtype':dtype,'shape':list(shape),'sha256':sha(path)}


def frozen_region_axis(origin,count,pitch,region_pitch):
    """Use the original scalar FP64 ordering,including its floor boundaries.

    Tensor/scalar division can multiply by a precomputed reciprocal. At the
    coarse physical scales that rounds some exact-integer boundaries to the
    other side. This small axis table uses Python's actual division instead;
    the GPU gathers stored integer coordinates and never reinterprets them.
    """
    return np.fromiter((math.floor(((i+.5)*pitch)/region_pitch)
        for i in range(origin,origin+count)),dtype=np.int64,count=count)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    parser.add_argument('--side-regions',type=int,default=16);parser.add_argument('--plan-only',action='store_true')
    args=parser.parse_args();assert sys.platform=='linux' and sys.byteorder=='little' and np.__version__=='1.26.4'
    from engine.hierarchical_specimen import HierarchicalSpecimen,PITCHES,HEIGHTS,CONTRAST,REGION_PITCH
    from engine.human_specimen_map import available_memory_bytes
    from engine.finite_catalog_format import load_header,array_chunks,PROTOCOL
    side=args.side_regions
    if type(side) is not int or side<1:raise ValueError('positive exact region count required')
    half=side*REGION_PITCH/2
    if not math.isfinite(half) or half>.05:raise ValueError('finite specimen must fit the qualified physical coordinate domain')
    directory=Path(args.output).resolve();workspace=ROOT
    if not directory.is_relative_to(workspace) or directory==workspace:raise ValueError('owned workspace output required')
    if directory.exists():raise ValueError('never overwrite an existing specimen or partial preparation')
    names=['engine/hierarchical_specimen.py','engine/human_alignment_specimen.py','engine/fine_practice_specimen.py',
        'engine/procedural_specimen.py','engine/finite_catalog_format.py','packages/numerics/counter_parameter_table.py',
        'scripts/prepare_finite_catalogue.py']
    before={n:sha(ROOT/n) for n in names}
    if before['packages/numerics/counter_parameter_table.py'] != 'c2a09beeb3adceb00c57dcdf2d054021da4cc494db4835617a5e8cb38996ea20':
        raise ValueError('Changed integer kernel requires independent requalification')
    specimen=HierarchicalSpecimen();levels=[]
    for pitch,height,contrast in zip(PITCHES,HEIGHTS,CONTRAST):
        lo=math.floor(-half/pitch)-1;hi=math.floor(half/pitch)+1;n=hi-lo+1
        levels.append({'origin':[lo,lo],'pitch_m':pitch.hex(),'height_m':height.hex(),'contrast':contrast.hex(),'axis':n})
    region_lo=math.floor(-half/REGION_PITCH);region_hi=math.floor(half/REGION_PITCH)
    region_axis=(np.arange(region_lo,region_hi+1)+.5)*REGION_PITCH
    x,y=np.meshgrid(region_axis,region_axis)
    regions=np.stack(specimen.material_codes(x,y)).astype(np.uint8)
    mask=(x>-half)&(x<half)&(y>-half)&(y<half)
    coverage=set(zip(*(plane[mask].tolist() for plane in regions)))
    if coverage!={(a,b,c) for a in range(3) for b in range(3) for c in range(3)}:
        raise ValueError('chosen existing region centres do not represent all27 private combinations')
    kinds={'particle':0.,'ridges':1.,'cross':2.,'terrace':3.}
    anchor=np.array([(f.x,f.y,f.rx,f.ry,f.angle,f.height,f.contrast,kinds[f.kind],f.period,f.phase,f.step_width)
        for f in specimen._anchor._features],dtype='<f8')
    required=sum(9*level['axis']**2*4 for level in levels)+anchor.nbytes+regions.nbytes
    nearest=directory.parent
    while not nearest.exists():nearest=nearest.parent
    storage=shutil.disk_usage(nearest)
    plan={'protocol':PROTOCOL,'width_m':2*half,'region_codes':len(coverage),'stored_feature_bytes':required,
        'level_axes':[level['axis'] for level in levels],'actual_disk_free_bytes':storage.free,
        'actual_available_host_bytes':available_memory_bytes(),'native_bitmap_claim':False}
    if args.plan_only:print(json.dumps(plan),flush=True);return
    if required>storage.free*.99:raise MemoryError('actual storage cannot admit this complete immutable catalogue')
    from runtime.prepared_resources import PreparedGpuLease
    directory.mkdir(parents=True,exist_ok=False);measurements=[];proof=None;begun=time.perf_counter()
    with PreparedGpuLease(ROOT) as lease:
        proof=lease.admit_device();os.environ['TRITON_CACHE_DIR']=str(ROOT/'.bootstrap-tmp/counter-triton-cache')
        import torch
        assert torch.__version__=='2.3.1+cu121'
        from packages.numerics.counter_parameter_table import counter_parameter_table
        for index,level in enumerate(levels):
            axis=level.pop('axis');count=axis*axis;path=directory/('level-'+str(index)+'.int32')
            start_time=time.perf_counter();batches=0;minimum=2**31-1;maximum=0
            pitch=float.fromhex(level['pitch_m'])
            region_x=torch.from_numpy(frozen_region_axis(level['origin'][0],axis,pitch,REGION_PITCH)).to('cuda:0')
            region_y=torch.from_numpy(frozen_region_axis(level['origin'][1],axis,pitch,REGION_PITCH)).to('cuda:0')
            with path.open('xb') as stream:
                stream.truncate(9*count*4);start=0
                while start<count:
                    free,_=torch.cuda.mem_get_info()
                    # Four coordinate vectors,output,and transient int/FP64 index
                    # work. This sizes work from actual host/GPU availability.
                    batch=int(min(free,available_memory_bytes())*.65//128)
                    if batch<1:raise MemoryError('actual GPU/host memory cannot admit catalogue work')
                    stop=min(count,start+batch);flat=torch.arange(start,stop,dtype=torch.int64,device='cuda:0')
                    ix=level['origin'][0]+flat%axis;iy=level['origin'][1]+flat//axis
                    rx=region_x[flat%axis];ry=region_y[flat//axis]
                    output=counter_parameter_table(ix,iy,rx,ry,order=index,seeds=specimen._seeds)
                    host=output.cpu().numpy();minimum=min(minimum,int(host.min()));maximum=max(maximum,int(host.max()))
                    assert host.dtype==np.dtype('<i4') and minimum>=0 and maximum<2147483647
                    for plane in range(9):
                        stream.seek((plane*count+start)*4);stream.write(memoryview(host[plane]).cast('B'))
                    del flat,ix,iy,rx,ry,output,host
                    start=stop;batches+=1
                stream.flush();os.fsync(stream.fileno())
            level['table']=entry(path,'<i4',(9,axis,axis))
            del region_x,region_y
            measurement={'level':index,'existing_cells':count,'bytes':path.stat().st_size,
                'batches':batches,'seconds':time.perf_counter()-start_time,'minimum_counter':minimum,'maximum_counter':maximum}
            measurements.append(measurement);print(json.dumps(measurement),flush=True)
        for name,values in (('anchor.float64',anchor),('regions.uint8',regions)):
            with (directory/name).open('xb') as stream:stream.write(values.tobytes());stream.flush();os.fsync(stream.fileno())
    after={n:sha(ROOT/n) for n in names};assert before==after,'frozen preparation source changed'
    manifest={'protocol':PROTOCOL,'bounds_m':[(-half).hex(),half.hex()]*2,'levels':levels,
        'anchor':entry(directory/'anchor.float64','<f8',anchor.shape),
        'regions':{'origin':[region_lo,region_lo],'pitch_m':REGION_PITCH.hex(),
            'table':entry(directory/'regions.uint8','|u1',regions.shape)},
        'background_phase':float(specimen._seeds[0]/2147483647).hex(),
        'source':{'generator_sha256':before['scripts/prepare_finite_catalogue.py'],
            'integer_kernel_sha256':before['packages/numerics/counter_parameter_table.py'],'profile':'generic-finite-low-relief-v1'}}
    temporary=directory/'manifest.tmp'
    with temporary.open('xb') as stream:
        stream.write((json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode());stream.flush();os.fsync(stream.fileno())
    temporary.rename(directory/'manifest.json');manifest_sha=sha(directory/'manifest.json')
    header=load_header(directory,manifest_sha)
    # Qualification deliberately rereads the final files,not a producer claim.
    for array in header.arrays:
        for _ in array_chunks(header,array):pass
    receipt={'status':'PREPARED_FINITE_CATALOGUE_FILES_VERIFIED','manifest_sha256':manifest_sha,
        'directory':str(directory),'plan':plan,'measurements':measurements,'seconds':time.perf_counter()-begun,
        'source_before':before,'source_after':after,'GPU_admission':proof,'actual_private_code_inventory':sorted(coverage),
        'runtime_no_growth_physics_or_human_release':False,'local_source_original_not_executed':True}
    path=directory.parent/(directory.name+'-preparation.json')
    with path.open('xb') as stream:stream.write((json.dumps(receipt,sort_keys=True,indent=2)+'\n').encode())
    print(json.dumps({'status':receipt['status'],'manifest_sha256':manifest_sha,'receipt':str(path),
        'stored_bytes':header.byte_count,'seconds':receipt['seconds']}),flush=True)


if __name__=='__main__':main()
