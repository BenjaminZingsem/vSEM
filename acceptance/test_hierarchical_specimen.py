"""Independent scalar,derivative,coverage and private material-code gates.

No statement that material codes activate damage/charging or constitute a SEM
acquisition. The procedural-field diagnostic is separately labelled as such.
"""
import random
import unittest
import numpy as np
from engine.hierarchical_specimen import HierarchicalSpecimen,PITCHES,REGION_PITCH
from engine.human_mapped_probe import emitted_and_collected


class HierarchicalFieldGates(unittest.TestCase):
    def setUp(self):self.specimen=HierarchicalSpecimen()

    def test_independent_scalar_vector_fields_agree_across_full_domain_and_anchor(self):
        rng=random.Random(201026)
        points=[(rng.uniform(-.05,.05),rng.uniform(-.05,.05)) for _ in range(32)]
        points += [(0.,0.),(.71e-6,-.36e-6),(-.65e-6,.37e-6),(.037e-6,-.029e-6)]
        x,y=np.array(points).T;actual=np.array(self.specimen.surface_arrays(x,y)).T
        expected=np.array([self.specimen.surface(float(a),float(b)) for a,b in points])
        np.testing.assert_allclose(actual[:,0],expected[:,0],rtol=2e-13,atol=2e-20)
        np.testing.assert_allclose(actual[:,1:3],expected[:,1:3],rtol=2e-11,atol=2e-11)
        np.testing.assert_allclose(actual[:,3],expected[:,3],rtol=2e-13,atol=2e-14)

    def test_surface_slopes_are_actual_height_derivatives(self):
        for x,y in ((.037e-6,-.029e-6),(.00412,.00337),(-.001023,-.002217),(.015123,.017337)):
            h=4e-11;z,sx,sy,_=self.specimen.surface(x,y)
            dx=(self.specimen.surface(x+h,y)[0]-self.specimen.surface(x-h,y)[0])/(2*h)
            dy=(self.specimen.surface(x,y+h)[0]-self.specimen.surface(x,y-h)[0])/(2*h)
            self.assertAlmostEqual(sx,dx,delta=5e-5)
            self.assertAlmostEqual(sy,dy,delta=5e-5)

    def test_all_scales_and_outer_regions_have_actual_height_and_signal_detail(self):
        centres=((0.,0.),(.000731,-.000427),(-.004137,.003171),(.021341,.019137))
        for centre in centres:
            for fov in (1e-6,20e-6,.001,.005):
                with self.subTest(centre=centre,fov=fov):
                    p=(np.arange(64)+.5-32)*fov/64
                    x,y=np.meshgrid(centre[0]+p,centre[1]+p)
                    fields=self.specimen.surface_arrays(x,y);emitted,collected=emitted_and_collected(fields)
                    self.assertGreater(float(np.percentile(fields[0],95)-np.percentile(fields[0],5)),.05e-9)
                    self.assertGreater(float(np.percentile(collected,95)-np.percentile(collected,5)),.001)
                    self.assertTrue(np.isfinite(emitted).all() and (emitted<=4).all())
                    self.assertTrue((collected>=0).all() and (collected<=emitted).all())

    def test_private_region_axes_cover_all_morphology_damage_conduction_combinations(self):
        p=(np.arange(-48,49)+.37)*REGION_PITCH;x,y=np.meshgrid(p,p)
        family,damage,conduction=self.specimen.material_codes(x,y)
        combos=set(zip(family.ravel().tolist(),damage.ravel().tolist(),conduction.ravel().tolist()))
        self.assertEqual(combos,{(a,b,c) for a in range(3) for b in range(3) for c in range(3)})
        self.assertEqual(len(combos),27)

    def test_query_partition_order_and_seed_do_not_redraw_a_world(self):
        x=np.linspace(-.003,.004,257);y=x*.23+17e-6
        first=np.array(self.specimen.surface_arrays(x,y));original=x.copy()
        split=np.concatenate([np.array(self.specimen.surface_arrays(x[:83],y[:83])),
            np.array(self.specimen.surface_arrays(x[83:],y[83:]))],axis=1)
        reverse=np.array(self.specimen.surface_arrays(x[::-1],y[::-1]))[:,::-1]
        np.testing.assert_allclose(first,split,rtol=2e-13,atol=2e-14)
        np.testing.assert_allclose(first,reverse,rtol=2e-13,atol=2e-14)
        np.testing.assert_array_equal(x,original)
        same=np.array(HierarchicalSpecimen().surface_arrays(x,y));np.testing.assert_array_equal(first,same)
        different=np.array(HierarchicalSpecimen(seed=b'another-private-construction').surface_arrays(x,y))
        self.assertGreater(float(np.max(np.abs(first[3]-different[3]))),.001)

    def test_cell_and_material_boundaries_do_not_introduce_surface_seams(self):
        for pitch in (*PITCHES,REGION_PITCH):
            x=pitch;y=.137*pitch;epsilon=1e-13
            a=np.array(self.specimen.surface(x-epsilon,y));b=np.array(self.specimen.surface(x+epsilon,y))
            self.assertLess(abs(a[0]-b[0]),3e-12)
            self.assertLess(abs(a[3]-b[3]),2e-5)

    def test_empty_scalar_and_broadcast_shapes_are_explicit(self):
        self.assertEqual(tuple(a.shape for a in self.specimen.surface_arrays([],[])),((0,),)*4)
        fields=self.specimen.surface_arrays(np.array([[1e-6],[2e-6]]),np.array([[3e-6,4e-6,5e-6]]))
        self.assertEqual(tuple(a.shape for a in fields),((2,3),)*4)
        self.assertEqual(tuple(a.shape for a in self.specimen.surface_arrays(0.,0.)),((),)*4)

    def test_invalid_coordinates_never_coerce_into_a_different_specimen(self):
        for x,y in ((True,0.),([False,1.],0.),('1',0.),(float('nan'),0.),(0.,float('inf')),(.056,0.),(0.,-.056)):
            with self.subTest(x=x,y=y):
                with self.assertRaises(ValueError):self.specimen.surface_arrays(x,y)


if __name__=='__main__':unittest.main()
