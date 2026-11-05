import math
import unittest
import numpy as np
from engine.beam_profile import Covariance2D
from engine.finite_edge_probe import conditional_material_rule
from engine.finite_absorption import finite_absorption


class FiniteEdgeRuleTests(unittest.TestCase):
    def test_positive_rules_match_independent_cdf_at_edges_and_corners(self):
        for rho in (-.95,0.,.95):
            c=Covariance2D(1600e-18,rho*800e-18,400e-18)
            for bounds in ((-1e-4,0.,-1e-4,1e-4),(-1e-4,0.,-1e-4,0.),(-11e-9,23e-9,-14e-9,37e-9)):
                x,y,p=conditional_material_rule(c,0.,0.,bounds,16)
                mass=finite_absorption(c,0.,0.,bounds)
                self.assertTrue(np.all(p>0));self.assertTrue(np.all((x>=bounds[0])&(x<=bounds[1])&(y>=bounds[2])&(y<=bounds[3])))
                self.assertAlmostEqual(math.fsum(p),mass.absorbed_probability,delta=3e-14)

    def test_nonzero_tiny_tail_is_kept_and_not_normalized(self):
        sigma=40e-9;c=Covariance2D(sigma*sigma,0.,sigma*sigma)
        bounds=(12*sigma,1e-4,-1e-4,1e-4)
        _,_,p=conditional_material_rule(c,0.,0.,bounds,16)
        actual=math.fsum(p);expected=.5*math.erfc(12/math.sqrt(2))
        self.assertGreater(actual,0.);self.assertAlmostEqual(actual/expected,1.,delta=3e-12)

    def test_remote_vacuum_has_no_field_nodes(self):
        c=Covariance2D(25e-18,0.,25e-18)
        x,y,p=conditional_material_rule(c,.001,0.,(-1e-4,1e-4,-1e-4,1e-4),8)
        self.assertEqual((len(x),len(y),len(p)),(0,0,0))


if __name__=='__main__':unittest.main()
