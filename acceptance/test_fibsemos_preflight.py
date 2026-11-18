"""Independent request-boundary cases; no fibsemOS import or emulation."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/fibsemos/src'))
from vsem_fibsemos.preflight import beam_write, image_request, stage_position


def request(**changes):
    return dict(resolution=(1024, 1024), dwell_time=20e-6, hfw=.001,
                autocontrast=False, beam_type='ELECTRON', save=False,
                filename='review', path=None, reduced_area=None,
                line_integration=None, scan_interlacing=None, frame_integration=None,
                drift_correction=False, bit_depth=None, **changes)


class RequestPreflightTests(unittest.TestCase):
    def test_explicit_native1024_does_not_rewrite_units_or_shape(self):
        self.assertEqual(image_request(request()),
                         {'width_px': 1024, 'height_px': 1024, 'dwell_s': 20e-6, 'hfw_m': .001})

    def test_upstream_defaults_fail_instead_of_adapting_resolution_or_dwell(self):
        for changes in ({'resolution': (1536, 1024)}, {'dwell_time': 1e-6},
                        {'resolution': (128, 256)}, {'beam_type': 'ION'}):
            value = request()
            value.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                image_request(value)

    def test_mixed_unsupported_request_is_rejected_as_a_whole(self):
        for key, values in {'save': [True, 0], 'autocontrast': [True, 0],
                            'drift_correction': [True], 'path': ['somewhere'],
                            'reduced_area': [{'left': .2, 'width': .2}],
                            'line_integration': [1, 2], 'frame_integration': [1, 2],
                            'scan_interlacing': [1, 2], 'bit_depth': [8, 16]}.items():
            for value in values:
                incoming = request()
                incoming[key] = value
                before = deepcopy(incoming)
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    image_request(incoming)
                self.assertEqual(incoming, before)

    def test_unknown_or_omitted_options_never_select_implicit_defaults(self):
        for key in request():
            incoming = request()
            del incoming[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                image_request(incoming)
        incoming = request()
        incoming['rotation'] = 0
        with self.assertRaises(ValueError):
            image_request(incoming)

    def test_original_current_is_checked_before_any_clipping_or_snapping(self):
        for current in (0, -1e-12, 1001e-12, 100.4e-12, True, float('nan'), float('inf')):
            with self.subTest(current=current), self.assertRaises(ValueError):
                beam_write('current', current)
        self.assertEqual(beam_write('current', 1e-12), 1e-12)
        self.assertEqual(beam_write('current', 1000e-12), 1e-9)
        for name in ('working_distance', 'voltage', 'hfw', 'on', 'unknown'):
            with self.assertRaises(ValueError):
                beam_write(name, 1)

    def test_stigmation_axes_are_signed_and_one_bad_axis_rejects_both(self):
        self.assertEqual(beam_write('stigmation', {'x': -.25, 'y': .5}), {'x': -.25, 'y': .5})
        for bad in ({'x': -.25, 'y': 1.01}, {'x': -.25}, {'x': 0, 'y': 0, 'z': 0},
                    {'x': True, 'y': 0}):
            with self.assertRaises(ValueError):
                beam_write('stigmation', bad)

    def test_stage_preserves_sign_and_requires_complete_declared_frame(self):
        value = dict(x=.001, y=-.002, z=1e-6, r=None, t=None,
                     coordinate_system='vsem_specimen_xyz_m', name=None)
        self.assertEqual(stage_position(value), dict(x_m=.001, y_m=-.002, z_m=1e-6,
                                                     frame='vsem_specimen_xyz_m'))
        for key, bad in (('x', None), ('z', 21e-6), ('r', 0), ('t', 0),
                         ('coordinate_system', None), ('coordinate_system', 'RAW')):
            with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                stage_position({**value, key: bad})


if __name__ == '__main__':
    unittest.main()
