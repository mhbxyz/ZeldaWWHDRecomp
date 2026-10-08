"""Benchmark statistics and profiler extraction tests; no game input."""
import unittest
from run_bench import logic_cpu_samples, run_statistics


class BenchmarkStatistics(unittest.TestCase):
    def test_ten_run_inclusive_quartiles(self):
        result = run_statistics(list(range(1, 11)))
        self.assertEqual(result['median'], 5.5)
        self.assertEqual((result['q1'], result['q3'], result['iqr']), (3.25, 7.75, 4.5))
        self.assertEqual(result['n'], 10)

    def test_single_run_has_zero_spread(self):
        result = run_statistics([4.0])
        self.assertEqual(result['iqr'], 0)
        self.assertEqual(result['stdev'], 0)

    def test_actual_logic_cpu_is_distinct_from_throughput(self):
        lines = ['[interp] 150.0 logic steps/s; main thread CPU per pass: logic 5.25 ms, blended hold 2.00 ms',
                 '[prof] frame 120: 120 frames, 6.00 ms/frame',
                 '[interp] 140.0 logic steps/s; main thread CPU per pass: logic 5.75 ms, blended hold 1.00 ms']
        self.assertEqual(logic_cpu_samples(lines), [5.25, 5.75])


if __name__ == '__main__':
    unittest.main()
