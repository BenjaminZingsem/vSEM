"""Independent format/corruption/missing-member gates,not physics activation."""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from engine.finite_catalog_format import load_header,array_chunks,ArraySpec

ROOT=Path(__file__).resolve().parents[1]


def sha(raw):return hashlib.sha256(raw).hexdigest()


class FiniteCatalogFormatGates(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'.bootstrap-tmp';parent.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='finite-format-',dir=parent)
        self.base=Path(self.temp.name).resolve();assert self.base.parent==parent.resolve()
        self.directory=self.base/'pack';self.directory.mkdir()
        def array(name,dtype,shape,raw):
            (self.directory/name).write_bytes(raw)
            return {'file':name,'dtype':dtype,'shape':shape,'sha256':sha(raw)}
        levels=[]
        for index in range(6):
            table=array('level-'+str(index)+'.int32','<i4',[9,5,5],bytes(9*5*5*4))
            levels.append({'origin':[-2,-2],'pitch_m':(80e-9*10**index).hex(),
                'height_m':(1e-9).hex(),'contrast':(.5).hex(),'table':table})
        anchor=array('anchor.float64','<f8',[1,11],struct.pack('<11d',0.,0.,1e-6,1e-6,0.,1e-9,0.,0.,40e-9,0.,3e-9))
        regions=array('regions.uint8','|u1',[3,2,2],bytes([0,1,2]*4))
        self.manifest={'protocol':'vsem.private.finite-feature-catalog.v1','bounds_m':[(-1e-9).hex(),(1e-9).hex()]*2,
            'levels':levels,'anchor':anchor,'regions':{'origin':[-1,-1],'pitch_m':(80e-6).hex(),'table':regions},
            'background_phase':(.25).hex(),'source':{'generator_sha256':'a'*64,'integer_kernel_sha256':'b'*64,
                'profile':'generic-finite-low-relief-v1'}}

    def tearDown(self):self.temp.cleanup()

    def header(self,manifest=None):
        raw=(json.dumps(self.manifest if manifest is None else manifest,sort_keys=True)+'\n').encode()
        (self.directory/'manifest.json').write_bytes(raw)
        return load_header(self.directory,sha(raw))

    def test_exact_stream_bytes_and_independent_content_hashes(self):
        header=self.header();self.assertEqual(len(header.arrays),8)
        total=0
        for item in header.arrays:
            actual=b''.join(array_chunks(header,item,7));expected=(self.directory/item.name).read_bytes()
            self.assertEqual(actual,expected);self.assertEqual(sha(actual),item.sha256);total+=len(actual)
        self.assertEqual(header.byte_count,total)

    def test_manifest_digest_required_before_interpreting_fields(self):
        self.header();before={p.name for p in self.directory.iterdir()}
        with self.assertRaises(ValueError):load_header(self.directory,'0'*64)
        self.assertEqual(before,{p.name for p in self.directory.iterdir()})

    def test_closed_fields_and_array_paths_never_redirect_a_read(self):
        for key,value in (('extra','x'),('seed','x'),('protocol','other')):
            m=copy.deepcopy(self.manifest);m[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.header(m)
        for name in ('../outside','/etc/passwd','level-0.int32/child','level-1.int32'):
            m=copy.deepcopy(self.manifest);m['levels'][0]['table']['file']=name
            with self.subTest(name=name),self.assertRaises(ValueError):self.header(m)

    def test_noncanonical_or_nonphysical_scalars_rejected(self):
        for scalar in ('nan','inf','0x1p+0',True,1.,' 0x1.0000000000000p-30 '):
            m=copy.deepcopy(self.manifest);m['levels'][0]['pitch_m']=scalar
            with self.subTest(scalar=scalar),self.assertRaises(ValueError):self.header(m)
        m=copy.deepcopy(self.manifest);m['bounds_m']=[(1e-9).hex(),(-1e-9).hex()]*2
        with self.assertRaises(ValueError):self.header(m)

    def test_missing_feature_or_material_support_is_not_generated(self):
        for target in ('levels','regions'):
            m=copy.deepcopy(self.manifest)
            if target=='levels':m['levels'][0]['origin']=[0,0]
            else:m['regions']['origin']=[0,0]
            with self.subTest(target=target),self.assertRaises(ValueError):self.header(m)
        self.header();(self.directory/'level-0.int32').unlink()
        with self.assertRaises(ValueError):self.header()
        self.assertFalse((self.directory/'level-0.int32').exists())

    def test_shape_and_size_corruption_rejected_before_large_allocation(self):
        for shape in ([9,True,5],[9,0,5],[8,5,5],[9,2**31-1,2**31-1]):
            m=copy.deepcopy(self.manifest);m['levels'][0]['table']['shape']=shape
            with self.subTest(shape=shape),self.assertRaises(ValueError):self.header(m)
        (self.directory/'level-0.int32').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.header()

    def test_content_corruption_after_header_fails_closed_at_end_of_stream(self):
        header=self.header();item=header.arrays[0];p=self.directory/item.name;raw=p.read_bytes()
        p.write_bytes(bytes([1])+raw[1:])
        with self.assertRaises(ValueError):list(array_chunks(header,item,13))

    def test_concurrent_change_is_not_an_admitted_snapshot(self):
        header=self.header();item=header.arrays[0];iterator=array_chunks(header,item,7);next(iterator)
        with (self.directory/item.name).open('r+b') as stream:stream.seek(-1,2);stream.write(b'X')
        with self.assertRaises(ValueError):list(iterator)

    def test_unknown_member_and_hardlink_rejected(self):
        (self.directory/'unexpected').write_bytes(b'extra')
        with self.assertRaises(ValueError):self.header()
        (self.directory/'unexpected').unlink()
        os.link(self.directory/'level-0.int32',self.base/'linked')
        with self.assertRaises(ValueError):self.header()

    def test_duplicate_json_fields_never_gain_last_key_authority(self):
        raw=json.dumps(self.manifest).encode();raw=b'{"protocol":"bad",'+raw[1:]
        (self.directory/'manifest.json').write_bytes(raw)
        with self.assertRaises(ValueError):load_header(self.directory,sha(raw))

    def test_direct_array_descriptor_cannot_escape_or_accept_mutable_shape(self):
        for name in ('../outside','/etc/passwd','level-6.int32','anchor.float64/child'):
            with self.subTest(name=name),self.assertRaises(ValueError):ArraySpec(name,'<i4',(1,),'a'*64)
        with self.assertRaises(ValueError):ArraySpec('level-0.int32','<i4',[1],'a'*64)

    def test_a_stream_cannot_substitute_a_foreign_array(self):
        header=self.header();other=ArraySpec('level-0.int32','<i4',(1,),'0'*64)
        with self.assertRaises(ValueError):list(array_chunks(header,other))


if __name__=='__main__':unittest.main()
