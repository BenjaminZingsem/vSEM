import math
import unittest
from unittest.mock import patch
from engine.beam_profile import Covariance2D
from engine.finite_absorption import finite_absorption
from engine.finite_fluence import finite_fluence
from engine.primary_fluence import rectangle_probability,primary_fluence


class FiniteFluenceTests(unittest.TestCase):
    def test_remote_vacuum_has_no_cell_work(self):
        cov=Covariance2D(25e-18,0.,25e-18)
        a=finite_absorption(cov,.001,0.,(-1e-4,1e-4,-1e-4,1e-4))
        with patch('engine.finite_fluence.rectangle_probability',side_effect=AssertionError('vacuum cell work')):
            f=finite_fluence(a)
        self.assertEqual((f.cells,f.unresolved_specimen_probability,a.escaped_probability),((),0.,1.))

    def test_deep_material_matches_original_partition(self):
        cov=Covariance2D(400e-18,30e-18,225e-18)
        a=finite_absorption(cov,0.,0.,(-1e-4,1e-4,-1e-4,1e-4))
        f=finite_fluence(a);old=primary_fluence(cov,0.,0.)
        self.assertEqual(len(f.cells),len(old.cells))
        for c,d in zip(f.cells,old.cells):
            self.assertEqual((c.index_x,c.index_y),(d.index_x,d.index_y))
            self.assertAlmostEqual(c.probability,d.probability,delta=3e-16)
        self.assertAlmostEqual(f.unresolved_specimen_probability,old.tail_probability,delta=1e-27)

    def test_clipped_cells_and_cdf_closure(self):
        for rho in (0.,.8,-.8):
            cov=Covariance2D(900e-18,rho*600e-18,400e-18)
            bounds=(-1e-4,7e-9,-1e-4,13e-9)
            a=finite_absorption(cov,0.,0.,bounds);f=finite_fluence(a)
            for c in f.cells:
                rect=f.cell_rectangle(c)
                self.assertLessEqual(rect[1],bounds[1]);self.assertLessEqual(rect[3],bounds[3])
                self.assertAlmostEqual(c.probability,rectangle_probability(cov,0.,0.,*rect),delta=4e-15)
            self.assertLessEqual(abs(math.fsum([c.probability for c in f.cells]+[f.unresolved_specimen_probability,-a.absorbed_probability])),8*math.ulp(a.absorbed_probability))

    def test_intercepted_tail_outside_eight_sigma_is_not_escape(self):
        cov=Covariance2D(25e-18,0.,25e-18)
        a=finite_absorption(cov,0.,0.,(60e-9,1e-4,-1e-4,1e-4));f=finite_fluence(a)
        self.assertGreater(a.absorbed_probability,0.)
        self.assertEqual(f.cells,());self.assertEqual(f.unresolved_specimen_probability,a.absorbed_probability)

    def test_rejects_fake_inputs(self):
        for value in (None,object(),()):
            with self.assertRaises(ValueError):finite_fluence(value)


if __name__=='__main__':unittest.main()
