"""Independent prefix/distribution criteria for the new conditional photon law."""
import unittest
import numpy as np
from engine.human_photon_prefix import CountProcess,WINDOW_MEAN,MAX_MEAN

SEED=bytes(range(32))
class HumanPhotonPrefixTests(unittest.TestCase):
    def test_zero_boundary_monotonic_and_query_order_reproducibility(self):
        values=(0.,.01,.7,1.,10.,500.,1000.,4095.9,4096.,4096.1,5000.,8192.,12000.)
        a=CountProcess(SEED,'episode:raster1',1048575,'SE')
        forward=[a.count(v) for v in values]
        b=CountProcess(SEED,'episode:raster1',1048575,'SE')
        reverse=[b.count(v) for v in reversed(values)][::-1]
        self.assertEqual(forward,reverse);self.assertEqual(forward,sorted(forward));self.assertEqual(forward[0],0)

    def test_complete_window_prefix_is_the_exact_root_count(self):
        process=CountProcess(SEED,'raster',1,'SE')
        self.assertEqual(process.count(WINDOW_MEAN),process._root(0))
        self.assertEqual(process.count(2*WINDOW_MEAN),process._root(0)+process._root(1))
        self.assertEqual(len(process._positions),0)

    def test_actual_poisson_mean_variance_and_independent_increments(self):
        samples=[]
        for index in range(6000):
            process=CountProcess(SEED,'statistics',index,'SE')
            a,b,c=process.count(10.),process.count(25.),process.count(80.)
            samples.append((a,b-a,c-b))
        values=np.asarray(samples,dtype=np.float64)
        expected=np.array([10.,15.,55.])
        means=values.mean(axis=0);variances=values.var(axis=0,ddof=1)
        np.testing.assert_array_less(np.abs(means-expected),7*np.sqrt(expected/6000))
        np.testing.assert_array_less(np.abs(variances-expected),7*expected*np.sqrt(2/5999))
        covariance=np.cov(values,rowvar=False)
        for i,j in ((0,1),(0,2),(1,2)):
            self.assertLess(abs(covariance[i,j]),7*np.sqrt(expected[i]*expected[j]/6000))

    def test_channel_raster_pixel_and_seed_are_distinct_closed_keys(self):
        tuples=[(SEED,'raster',1,'SE'),(SEED,'raster',2,'SE'),(SEED,'other',1,'SE'),
                (SEED,'raster',1,'BSE'),(bytes(32),'raster',1,'SE')]
        rows=[tuple(CountProcess(*args).count(v) for v in (10.,100.,1000.,5000.)) for args in tuples]
        self.assertEqual(len(set(rows)),len(rows))

    def test_increments_across_intensity_window_boundaries_are_independent(self):
        samples=[]
        for index in range(4000):
            process=CountProcess(SEED,'window-statistics',index,'SE')
            a,b,c=process.count(3900.),process.count(4900.),process.count(8900.)
            samples.append((a,b-a,c-b))
        values=np.asarray(samples,dtype=np.float64);expected=np.array([3900.,1000.,4000.])
        np.testing.assert_array_less(np.abs(values.mean(axis=0)-expected),7*np.sqrt(expected/4000))
        np.testing.assert_array_less(np.abs(values.var(axis=0,ddof=1)-expected),
                                     7*np.sqrt((2*expected**2+expected)/3999))
        covariance=np.cov(values,rowvar=False)
        for i,j in ((0,1),(0,2),(1,2)):
            self.assertLess(abs(covariance[i,j]),7*np.sqrt(expected[i]*expected[j]/4000))

    def test_invalid_inputs_and_unsigned_representation_are_not_coerced(self):
        for args in ((bytearray(32),'raster',1,'SE'),(SEED,'raster',True,'SE'),
                     (SEED,'bad/identity',1,'SE'),(SEED,'raster',16777216,'SE'),(SEED,'raster',1,'se')):
            with self.subTest(args=repr(args)),self.assertRaises(ValueError):CountProcess(*args)
        process=CountProcess(SEED,'raster',1,'SE')
        for value in (True,-1,float('nan'),float('inf'),MAX_MEAN+1,np.float64(2)):
            with self.subTest(value=repr(value)),self.assertRaises(ValueError):process.count(value)
        self.assertIs(type(process.count(1000.)),int)

if __name__=='__main__':unittest.main()
