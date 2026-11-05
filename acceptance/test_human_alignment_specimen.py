"""New patterned subject:derivatives,source convergence and actual probe detail."""
import unittest
import numpy as np
from engine.human_alignment_specimen import HumanAlignmentSpecimen
from engine.human_specimen_map import NativeWorldMap
from engine.human_mapped_probe import build_probe_bank,direct_analytic_coefficient
from engine.human_episode_types import EpisodeGeometry,EpisodeSettings

class HumanAlignmentSpecimenTests(unittest.TestCase):
    def test_independent_scalar_vector_surface_agreement(self):
        rng=np.random.default_rng(144);points=rng.uniform(-1e-6,1e-6,(600,2))
        source=HumanAlignmentSpecimen()
        scalar=np.array([source.surface(float(x),float(y)) for x,y in points]).T
        vector=np.array(source.surface_arrays(points[:,0],points[:,1]))
        np.testing.assert_allclose(scalar,vector,rtol=2e-12,atol=1e-15)
        self.assertTrue(np.all(np.abs(vector[0])<=.55e-6))
        self.assertTrue(np.all((vector[3]>=.12)&(vector[3]<=.32)))

    def test_surface_slopes_match_independent_finite_differences_at_edges(self):
        source=HumanAlignmentSpecimen();step=1e-12
        for x,y in ((-.75e-6,0.),(-.61e-6,.3e-6),(.575e-6,-.17e-6),(.35e-6,.54e-6),(.07e-6,.1e-6)):
            _,sx,sy,_=source.surface(x,y)
            dx=(source.surface(x+step,y)[0]-source.surface(x-step,y)[0])/(2*step)
            dy=(source.surface(x,y+step)[0]-source.surface(x,y-step)[0])/(2*step)
            self.assertAlmostEqual(sx,dx,delta=1e-6)
            self.assertAlmostEqual(sy,dy,delta=1e-6)

    def test_fine_map_probe_agrees_with_scalar_reference_at_patterned_edges(self):
        world=NativeWorldMap(specimen=HumanAlignmentSpecimen(),spacing_m=1.25e-9)
        geometry=EpisodeGeometry(64,64,2e-6)
        for settings in (EpisodeSettings(100,1.2e-6,.18,-.12),EpisodeSettings(100,-20e-6,.18,-.12),
                         EpisodeSettings(100,-8e-6,.8,-.7)):
            bank=build_probe_bank(world,geometry,settings)
            for index in (535,823,1247,1856,2150,2553,3262):
                direct=direct_analytic_coefficient(world.specimen,geometry,settings,index)
                self.assertLess(abs(bank.coefficient(index)-direct)/direct,.005)

    def test_patterned_focused_field_is_discernible_and_defocus_removes_edge_detail(self):
        world=NativeWorldMap(specimen=HumanAlignmentSpecimen(),spacing_m=1.25e-9)
        geometry=EpisodeGeometry(128,128,2e-6)
        a=build_probe_bank(world,geometry,EpisodeSettings(100,1.2e-6,.18,-.12)).se_collected_per_incident.reshape(128,128)
        b=build_probe_bank(world,geometry,EpisodeSettings(100,-23e-6,.18,-.12)).se_collected_per_incident.reshape(128,128)
        sharp=float(np.mean(np.diff(a,axis=0)**2)+np.mean(np.diff(a,axis=1)**2))
        soft=float(np.mean(np.diff(b,axis=0)**2)+np.mean(np.diff(b,axis=1)**2))
        self.assertGreater(sharp,4*soft)
        self.assertGreater(float(np.std(a-b)),.003)
        self.assertGreater(float(a.max()-a.min()),.06)

if __name__=='__main__':unittest.main()
