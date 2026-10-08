"""Benchmark statistics and profiler extraction tests; no game input."""
import unittest
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock
from run_bench import benchmark_pids, logic_cpu_samples, quiet_reasons, run_statistics


class BenchmarkStatistics(unittest.TestCase):
    def test_ten_run_inclusive_quartiles(self):
        result = run_statistics(list(range(1, 11)))
        self.assertEqual(result['median'], 5.5)
        self.assertEqual((result['q1'], result['q3'], result['iqr']), (3.25, 7.75, 4.5))
        self.assertEqual(result['n'], 10)

    def test_benchmark_detection_excludes_self_and_shell_wrappers(self):
        listing = """101 /usr/bin/python3 /repo/tools/bench/run_bench.py --runs 10
102 /usr/bin/python3 /other/run_bench.py --runs 2
103 /bin/zsh -lc 'python3 /repo/tools/bench/run_bench.py'
104 /usr/bin/python3 /repo/tools/bench/test_run_bench.py
105 /usr/bin/wwhd --game /game
"""
        self.assertEqual(benchmark_pids(listing, 101), [102])

    def test_quiet_gate_checks_strict_load_and_disk_reserve(self):
        args = SimpleNamespace(quiet_load_max=12, exclusive_bench=False, min_free_gb=15, out='build')
        with mock.patch('run_bench.load1', return_value=12), mock.patch('run_bench.shutil.disk_usage', return_value=SimpleNamespace(free=14e9)):
            reasons = quiet_reasons(args)
            self.assertEqual(len(reasons), 2)
        with mock.patch('run_bench.load1', return_value=11.99), mock.patch('run_bench.shutil.disk_usage', return_value=SimpleNamespace(free=16e9)):
            self.assertEqual(quiet_reasons(args), [])

    @unittest.skipIf(os.name == 'nt', 'fixture executables use POSIX shebangs')
    def test_cli_runs_distinct_binaries_and_records_logic_cpu(self):
        repo = Path(__file__).resolve().parents[2]
        (repo / 'build').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='bench-fixture-', dir=repo / 'build') as directory:
            root = Path(directory)
            for name in ['save', 'states', 'game']:
                (root / name).mkdir()
            (root / 'states/slot1.bin').touch()  # synthetic empty fixture, never loaded by a game
            executables = []
            for name, frame, cpu in [('a', 6, 4), ('b', 8, 5)]:
                executable = root / name
                log = '[fixture] Loaded slot 1\n'
                log += f'[prof] frame 120: 120 frames (0 hold), {frame}.00 ms/frame, 150.0 swaps/s, 150.0 logic steps/s; render thread CPU 3.00 ms/frame, in ops 2.00 ms/frame, idle (waiting for commands) 1.00 ms/frame\n'
                log += (f'[interp] main thread CPU per pass: logic {cpu}.00 ms\n' * 3)
                executable.write_text('#!' + sys.executable + '\nprint(' + repr(log) + ')\n')
                executable.chmod(0o755)
                executables.append(executable)
            command = [sys.executable, str(repo / 'tools/bench/run_bench.py'),
                       '--binary', str(executables[0]), '--variant', 'a:', '--variant', 'b:',
                       '--variant-binary', 'b=' + str(executables[1]),
                       '--save', str(root / 'save'), '--state-dir', str(root / 'states'),
                       '--game', str(root / 'game'), '--scene', 'still', '--runs', '1',
                       '--out', str(root / 'out'), '--skip-windows', '0', '--no-wait', '--no-watch']
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((root / 'out/summary.json').read_text())
            self.assertEqual([run['status'] for run in report['runs']], ['ok', 'ok'])
            self.assertEqual([Path(run['binary']).name for run in report['runs']], ['a', 'b'])
            self.assertEqual(report['variants']['a']['frame_ms']['median'], 6)
            self.assertEqual(report['variants']['b']['logic_cpu_ms']['median'], 5)

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
