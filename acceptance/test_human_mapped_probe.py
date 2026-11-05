"""Independent analytic beam checks for the new cached world-map response."""
import unittest
import numpy as np
from engine.human_episode_types import EpisodeGeometry,EpisodeSettings
from engine.human_specimen_map import NativeWorldMap
from engine.human_mapped_probe import (HumanMappedProfile,build_probe_bank,
    direct_analytic_coefficient,effective_settings)

class HumanMappedProbeTests(unittest.TestCase):
    def test_physical_mapped_coefficients_agree_with_scalar_analytic_oracle(self):
        world=NativeWorldMap();geometry=EpisodeGeometry(48,48,1.5e-6)
        indices=(0,207,533,800,1023,1530,1801,2303)
        for settings in (EpisodeSettings(100,1.2e-6,.18,-.12),EpisodeSettings(100,-22e-6,.18,-.12),
                         EpisodeSettings(100,-8e-6,.8,-.7)):
            bank=build_probe_bank(world,geometry,settings)
            for index in indices:
                direct=direct_analytic_coefficient(world.specimen,geometry,settings,index)
                self.assertLess(abs(bank.coefficient(index)-direct)/direct,.005)

    def test_focus_changes_actual_response_contrast_in_fixed_world_geometry(self):
        world=NativeWorldMap();geometry=EpisodeGeometry(128,128,1.5e-6)
        focused=build_probe_bank(world,geometry,EpisodeSettings(100,1.2e-6,.18,-.12))
        blurred=build_probe_bank(world,geometry,EpisodeSettings(100,-23e-6,.18,-.12))
        a,b=focused.se_collected_per_incident.reshape(128,128),blurred.se_collected_per_incident.reshape(128,128)
        sharp=float(np.mean(np.diff(a,axis=0)**2)+np.mean(np.diff(a,axis=1)**2))
        soft=float(np.mean(np.diff(b,axis=0)**2)+np.mean(np.diff(b,axis=1)**2))
        self.assertGreater(sharp,2*soft)
        self.assertGreater(float(np.std(a-b)),.001)
        self.assertEqual(focused.geometry,blurred.geometry)

    def test_z_lens_compensation_preserves_response_with_distinct_actual_geometry(self):
        world=NativeWorldMap();g=EpisodeGeometry(64,64,1.5e-6)
        z=EpisodeGeometry(64,64,1.5e-6,stage_z_m=2**-18)
        a=build_probe_bank(world,g,EpisodeSettings(100,2**-20,.18,-.12))
        b=build_probe_bank(world,z,EpisodeSettings(100,2**-20-2**-18,.18,-.12))
        np.testing.assert_array_equal(a.se_collected_per_incident,b.se_collected_per_incident)
        self.assertNotEqual(a.source_identity,b.source_identity)

    def test_roi_and_parent_share_response_at_same_native_world_points(self):
        world=NativeWorldMap();settings=EpisodeSettings(100,-5e-6,.5,.3)
        parent=build_probe_bank(world,EpisodeGeometry(128,128,4e-6),settings)
        roi=build_probe_bank(world,EpisodeGeometry(32,32,1e-6),settings)
        a=parent.se_collected_per_incident.reshape(128,128)[48:80,48:80]
        b=roi.se_collected_per_incident.reshape(32,32)
        np.testing.assert_allclose(a,b,rtol=0,atol=2e-13)

    def test_astigmatic_under_overfocus_rotates_probe_axes_and_changes_field(self):
        profile=HumanMappedProfile();world=NativeWorldMap();g=EpisodeGeometry(64,64,1.5e-6)
        under=EpisodeSettings(100,1.2e-6-10e-6,.7,.3)
        over=EpisodeSettings(100,1.2e-6+10e-6,.7,.3)
        cu=profile.covariance(effective_settings(under,g),0.)
        co=profile.covariance(effective_settings(over,g),0.)
        self.assertAlmostEqual(cu.xx_m2,co.yy_m2,delta=1e-27)
        self.assertAlmostEqual(cu.yy_m2,co.xx_m2,delta=1e-27)
        self.assertAlmostEqual(cu.xy_m2,-co.xy_m2,delta=1e-27)
        a=build_probe_bank(world,g,under);b=build_probe_bank(world,g,over)
        self.assertGreater(float(np.std(a.se_collected_per_incident-b.se_collected_per_incident)),.0005)

    def test_native_1024_bank_has_immutable_original_response_samples(self):
        world=NativeWorldMap();g=EpisodeGeometry(1024,1024,4e-6)
        bank=build_probe_bank(world,g,EpisodeSettings(100,1.2e-6,.18,-.12))
        self.assertEqual(bank.se_collected_per_incident.shape,(1048576,))
        self.assertFalse(bank.se_collected_per_incident.flags.writeable)
        for index in (0,1032,100087,524288,1048575):
            direct=direct_analytic_coefficient(world.specimen,g,bank.settings,index)
            self.assertLess(abs(bank.coefficient(index)-direct)/direct,.005)
        self.assertGreater(float(np.std(bank.se_collected_per_incident)),.001)

if __name__=='__main__':unittest.main()
