"""Closed finite startup;inherited physical clocks,transports and public state."""
import ast
import hashlib
from pathlib import Path
import tempfile
import unittest
from runtime import hierarchical_human_kernel as old
from runtime import finite_human_kernel as new
from runtime.hierarchical_human_service import InteractiveHumanService,ObservedKernel
from runtime.finite_human_service import FiniteHumanService,ObservedFiniteKernel
from runtime.finite_launch_spec import FrozenFiniteLaunch,finite_launch_option
from runtime.hierarchical_public_protocol import validate_command

ROOT=Path(__file__).resolve().parents[1]


def tree(name):return ast.parse((ROOT/'runtime'/name).read_bytes())
def shape(node):return ast.dump(node,include_attributes=False)
def method(name,cls,func):
    c=next(n for n in tree(name).body if isinstance(n,ast.ClassDef) and n.name==cls)
    return next(n for n in c.body if isinstance(n,ast.FunctionDef) and n.name==func)


class FiniteRuntimeBoundaryTests(unittest.TestCase):
    def test_every_existing_kernel_operation_is_inherited_unchanged(self):
        for name in ('refresh','_retain','close','submit','elapsed_ns','fault','read_image'):
            self.assertIs(getattr(new.FiniteLiveRealtimeKernel,name),getattr(old.LiveRealtimeKernel,name))
        self.assertEqual({n.name for n in next(n for n in tree('finite_human_kernel.py').body if isinstance(n,ast.ClassDef)).body if isinstance(n,ast.FunctionDef)}, {'__init__'})

    def test_physical_owner_verifier_mailbox_and_configuration_are_original(self):
        for name in ('owner_worker','PacedCausalVerifier','ScalarMailbox','ReservedMailbox','Wire','LiveKernelConfiguration'):
            self.assertIs(getattr(new,name),getattr(old,name))
        self.assertIs(ObservedFiniteKernel.__init__,ObservedKernel.__init__)
        self.assertTrue(issubclass(ObservedFiniteKernel,new.FiniteLiveRealtimeKernel))

    def test_constructor_diff_is_only_closed_finite_numerical_startup(self):
        a=method('hierarchical_human_kernel.py','LiveRealtimeKernel','__init__')
        b=method('finite_human_kernel.py','FiniteLiveRealtimeKernel','__init__')
        self.assertEqual([n.arg for n in b.args.kwonlyargs],['finite_catalogue','seed'])
        b.args.kwonlyargs.pop(0);b.args.kw_defaults.pop(0)
        self.assertEqual(ast.unparse(b.body[0]),'t.exact(finite_catalogue, FrozenFiniteLaunch)')
        self.assertEqual(ast.unparse(b.body[1]),'finite_catalogue.__post_init__()')
        b.body=b.body[2:]
        process=next(n for n in ast.walk(b) if isinstance(n,ast.Call) and ast.unparse(n.func)=='self.context.Process' and any(k.arg=='target' and ast.unparse(k.value)=='numerical_worker' for k in n.keywords))
        args=next(k.value for k in process.keywords if k.arg=='args')
        self.assertEqual(ast.unparse(args.elts[-1]),'finite_catalogue');args.elts.pop()
        self.assertEqual(shape(a),shape(b))

    def test_original_numerical_fact_count_and_native_publication_loop_is_identical(self):
        loops=[]
        for name in ('hierarchical_human_numerics.py','finite_human_numerics.py'):
            func=next(n for n in tree(name).body if isinstance(n,ast.FunctionDef) and n.name=='_numerical_worker')
            loops.append(next(n for n in func.body if isinstance(n,ast.While)))
        self.assertEqual(shape(loops[0]),shape(loops[1]))

    def test_every_service_command_observation_and_artifact_method_is_original(self):
        for name in ('request','_admit','_event','_run','snapshot','operation','image','close'):
            self.assertIs(getattr(FiniteHumanService,name),getattr(InteractiveHumanService,name))

    def test_no_cuda_or_physical_arrays_enter_scalar_or_transport_adapters(self):
        for name in ('finite_launch_spec.py','finite_human_kernel.py','finite_human_service.py'):
            imports=[n.module for n in ast.walk(tree(name)) if isinstance(n,ast.ImportFrom)]
            imports += [a.name for n in ast.walk(tree(name)) if isinstance(n,ast.Import) for a in n.names]
            self.assertFalse(any(v and v.split('.')[0] in ('torch','triton','numpy','scipy') for v in imports))

    def test_finite_assets_require_explicit_no_generation_option(self):
        self.assertIsNone(finite_launch_option(no_world_generation=False,catalogue_directory=None,manifest_sha256=None))
        for args in ((False,'asset','a'*64),(True,None,None),(True,'asset',None),(1,None,None)):
            with self.assertRaises(ValueError):finite_launch_option(no_world_generation=args[0],catalogue_directory=args[1],manifest_sha256=args[2])

    def test_existing_changed_and_missing_manifests_fail_closed_without_generation(self):
        base=ROOT/'.bootstrap-tmp';base.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as directory:
            p=Path(directory).resolve();manifest=p/'manifest.json';manifest.write_bytes(b'{}\n')
            digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
            value=finite_launch_option(no_world_generation=True,catalogue_directory=str(p),manifest_sha256=digest)
            self.assertIs(type(value),FrozenFiniteLaunch);self.assertFalse(value.world_generation_allowed)
            manifest.write_bytes(b'{"changed":true}\n')
            with self.assertRaises(ValueError):value.__post_init__()
            manifest.unlink()
            with self.assertRaises(ValueError):FrozenFiniteLaunch(str(p),digest)

    def test_catalogue_and_generation_controls_are_not_operator_commands(self):
        for key in ('catalogue_directory','manifest_sha256','no_world_generation','world_generation_allowed','material_codes'):
            command={'action':'scan_live','parameters':{'width_px':64,'height_px':64,'field_width_m':.001,
                'offset_x_m':0.,'offset_y_m':0.,'dwell_ns':20000,key:'forbidden'},'expected_stop_generation':0}
            with self.assertRaises(ValueError):validate_command(command)


if __name__=='__main__':unittest.main()
