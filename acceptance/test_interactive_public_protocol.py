"""Independent observable whitelist for the explicitly identified stage variant."""
import copy
import json
import unittest
from runtime.interactive_public_protocol import image_observation,validate_command
from acceptance.test_core_public_protocol import metadata


def private_image():
    value=metadata(20_065_000);value['protocol']='vsem.private.native-image-cut.v2'
    first=copy.deepcopy(value['configuration']['geometry'])
    second={**first,'stage_x_m':8e-6,'stage_z_m':1e-6,'seed':'HIDDEN','potential':'HIDDEN'}
    s=value['applied_segments'][0]
    value['applied_segments']=[{**s,'end_elapsed_ns':30_000_000,'geometry':first},
        {**s,'start_elapsed_ns':30_000_000,'geometry':second}]
    value['current_configuration']={'geometry':second,'dwell_ns':20000}
    return value


class InteractivePublicGates(unittest.TestCase):
    def test_initial_and_applied_stage_are_explicit_observations(self):
        source=private_image();before=copy.deepcopy(source);value=image_observation(source)
        self.assertEqual(value['protocol'],'vsem.core-native-image.v2')
        self.assertEqual(value['stage']['x_m'],1e-6)
        self.assertEqual([s['stage']['x_m'] for s in value['parameter_segments']],[1e-6,8e-6])
        self.assertEqual(value['parameter_segments'][1]['stage']['working_distance_m'],.010-1e-6)
        self.assertEqual(source,before)

    def test_hidden_fields_never_leak_through_mixed_segments(self):
        source=private_image();value=image_observation(source);raw=json.dumps(value)
        self.assertNotIn('HIDDEN',raw)
        for name in ('seed','potential','world_height','ideal_focus','expected_rate','current_configuration','geometry'):
            self.assertNotIn(name,raw)
        keys={'start_elapsed_ns','end_elapsed_ns','current_pA','focus_offset_m','stigmator_x','stigmator_y','stage'}
        self.assertTrue(all(set(s)==keys for s in value['parameter_segments']))

    def test_wrong_private_version_is_rejected(self):
        source=private_image();source['protocol']='vsem.private.native-image-cut.v1'
        with self.assertRaises(ValueError):image_observation(source)

    def test_unqualified_wide_FOV_is_not_admitted_by_new_stage_variant(self):
        command={'action':'scan_live','parameters':{'width_px':64,'height_px':64,'field_width_m':5e-3,
            'offset_x_m':0.,'offset_y_m':0.,'dwell_ns':20000},'expected_stop_generation':0}
        with self.assertRaises(ValueError):validate_command(command)
        command['parameters']['field_width_m']=2e-6
        self.assertEqual(validate_command(command),command)


if __name__=='__main__':unittest.main()
