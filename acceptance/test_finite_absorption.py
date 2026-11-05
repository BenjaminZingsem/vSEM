"""Analytic finite Gaussian interception/positive escape and charge gates."""
import math
import unittest
from engine.beam_profile import Covariance2D
from engine.finite_absorption import finite_absorption,split_incident_charge


class FiniteAbsorptionGates(unittest.TestCase):
    def test_finite_remote_vacuum_is_exact_zero_with_full_primary_escape(self):
        covariance=Covariance2D((40e-9)**2,0.,(60e-9)**2)
        for x,y in ((.001,0.),(-.001,0.),(0.,.01),(.055,.055)):
            mass=finite_absorption(covariance,x,y,(-.00064,.00064,-.00064,.00064))
            self.assertEqual((mass.absorbed_probability,mass.escaped_probability),(0.,1.))
            self.assertEqual(split_incident_charge(2e-15,mass),(0.,2e-15))

    def test_deep_interior_is_full_material_interception(self):
        mass=finite_absorption(Covariance2D(1e-16,0.,4e-16),0.,0.,(-.00064,.00064,-.00064,.00064))
        self.assertEqual((mass.absorbed_probability,mass.escaped_probability),(1.,0.))

    def test_diagonal_rectangle_matches_independent_erf_product(self):
        sx,sy=40e-9,60e-9;cx,cy=7e-9,-11e-9;bounds=(-32e-9,54e-9,-27e-9,83e-9)
        expected=.25*(math.erf((bounds[1]-cx)/(math.sqrt(2)*sx))-math.erf((bounds[0]-cx)/(math.sqrt(2)*sx)))*\
            (math.erf((bounds[3]-cy)/(math.sqrt(2)*sy))-math.erf((bounds[2]-cy)/(math.sqrt(2)*sy)))
        mass=finite_absorption(Covariance2D(sx*sx,0.,sy*sy),cx,cy,bounds)
        self.assertAlmostEqual(mass.absorbed_probability,expected,delta=2e-15)

    def test_correlated_quadrants_match_asin_identity(self):
        variance=(40e-9)**2
        for rho in (-.9,-.5,0.,.5,.9):
            covariance=Covariance2D(variance,rho*variance,variance)
            mass=finite_absorption(covariance,0.,0.,(0.,2e-6,0.,2e-6))
            self.assertAlmostEqual(mass.absorbed_probability,.25+math.asin(rho)/(2*math.pi),delta=2e-12)

    def test_half_plane_is_half_even_with_correlation(self):
        variance=(40e-9)**2
        for rho in (-.9,0.,.9):
            mass=finite_absorption(Covariance2D(variance,rho*variance,variance),0.,0.,(0.,2e-6,-2e-6,2e-6))
            self.assertAlmostEqual(mass.absorbed_probability,.5,delta=2e-12)

    def test_tiny_positive_escape_is_not_subtracted_from_nearly_one(self):
        sigma=40e-9
        mass=finite_absorption(Covariance2D(sigma*sigma,0.,sigma*sigma),0.,0.,(-8*sigma,2e-6,-2e-6,2e-6))
        expected=.5*math.erfc(8/math.sqrt(2))
        self.assertGreater(mass.escaped_probability,0.)
        self.assertAlmostEqual(mass.escaped_probability/expected,1.,delta=2e-11)

    def test_charge_partition_closes_across_tiny_and_large_currents(self):
        covariance=Covariance2D((40e-9)**2,0.,(60e-9)**2)
        for x in (-.001,-20e-9,0.,20e-9,.001):
            mass=finite_absorption(covariance,x,0.,(0.,2e-6,-2e-6,2e-6))
            for q in (0.,1e-30,2e-15,1e-9,1.):
                a,e=split_incident_charge(q,mass)
                self.assertGreaterEqual(min(a,e),0.)
                self.assertLessEqual(abs(math.fsum((a,e,-q))),8*math.ulp(q)+1e-30)

    def test_invalid_domain_and_exact_types_fail_without_a_source(self):
        covariance=Covariance2D(1e-16,0.,1e-16)
        for bounds in (None,[0.,1e-6,0.,1e-6],(0.,0.,0.,1e-6),(True,1e-6,0.,1e-6),(-.051,.051,0.,1e-6)):
            with self.subTest(bounds=bounds),self.assertRaises(ValueError):finite_absorption(covariance,0.,0.,bounds)
        with self.assertRaises(ValueError):finite_absorption(Covariance2D(1e-20,0.,1e-20),0.,0.,(0.,1e-6,0.,1e-6))


if __name__=='__main__':unittest.main()
