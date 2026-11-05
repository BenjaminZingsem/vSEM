"""Independent public whitelist,recorded-pixel exposure and command boundaries."""
import unittest
from runtime.core_public_protocol import image_observation,validate_command

def metadata(cursor):
    return {'image_id':'image-1','live_view_id':'view-1','causal_raster_id':'raster-1','mode':'LIVE',
        'outcome':'ACQUIRING','terminal_reason':None,'origin_ns':123,'elapsed_ns':cursor+50_000_000,'nominal_ns':cursor,
        'numerical_ordinal':3,'configuration':{'geometry':{'width_px':64,'height_px':64,'field_width_m':2e-6,
            'stage_x_m':1e-6,'stage_y_m':2e-6,'stage_z_m':3e-6,'offset_x_m':.2e-6,'offset_y_m':-.1e-6},'dwell_ns':20000},
        'applied_segments':[{'start_elapsed_ns':0,'end_elapsed_ns':cursor+50_000_000,
            'settings':{'current_pA':100,'focus_offset_m':1.2e-6,'stigmator_x':.18,'stigmator_y':-.12}}],
        'blank_holds':[{'start_elapsed_ns':0,'end_elapsed_ns':50_000_000}], 'incident_pA_ns':1000,
        'seed':'never_project','world_height':'never_project','ideal_focus':'never_project','expected_rate':'never_project'}

class PublicProtocolTests(unittest.TestCase):
    def test_partial_dwell_is_recorded_active_exposure_not_hold_wall_time(self):
        value=image_observation(metadata(20_000_000+3*20000+5000))
        self.assertEqual((value['completed_pixels'],value['active_dwell_ns']),(3,5000))
        self.assertEqual(value['pixel_pitch_m'],2e-6/64)
        self.assertAlmostEqual(value['magnification'],50000,places=8)
        self.assertEqual(value['stage']['working_distance_m'],.010-3e-6)
    def test_settling_flyback_and_complete_masks(self):
        for cursor,completed,active in ((10_000_000,0,0),(20_000_000+64*20000+50000,64,0),
                (20_000_000+64*64*20000+63*100000+10000000,4096,0)):
            value=image_observation(metadata(cursor));self.assertEqual((value['completed_pixels'],value['active_dwell_ns']),(completed,active))
    def test_hidden_private_fields_never_project(self):
        value=image_observation(metadata(20_000_000))
        for key in ('seed','world_height','ideal_focus','expected_rate','source_digest','pid'):self.assertNotIn(key,value)
        self.assertEqual(value['causal_verified_ordinal'],value['numerical_verified_ordinal'])
        self.assertEqual(value['parameter_segments'][0]['focus_offset_m'],1.2e-6)
    def test_supported_native1024_command_is_exact_and_does_not_mutate(self):
        value={'action':'scan_single','parameters':{'width_px':1024,'height_px':1024,'field_width_m':2e-6,
            'offset_x_m':0.,'offset_y_m':0.,'dwell_ns':20000},'expected_stop_generation':0}
        copy=validate_command(value);self.assertEqual(copy,value);self.assertIsNot(copy['parameters'],value['parameters'])
    def test_unknown_role_and_unimplemented_physical_controls_reject(self):
        for action in ('set_hv','set_vacuum','tilt','rotation','auto_focus','truth'):
            with self.assertRaises(ValueError):validate_command({'action':action,'parameters':{},'expected_stop_generation':0})
    def test_nonfinite_wrong_types_ranges_extra_fields_and_stale_source_shape_reject(self):
        for value in (float('nan'),True,'0',.00003):
            with self.assertRaises(ValueError):validate_command({'action':'stage_move','parameters':{'x_m':0.,'y_m':0.,'z_m':value},'expected_stop_generation':0})
        with self.assertRaises(ValueError):validate_command({'action':'stop','parameters':{'holder_id':'forged'},'expected_stop_generation':0})
        with self.assertRaises(ValueError):validate_command({'action':'stop','parameters':{},'expected_stop_generation':True})

if __name__=='__main__':unittest.main()
