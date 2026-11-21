import sys
import time
import unittest


class NoisyHangTests(unittest.TestCase):
    def test_prints_then_hangs(self):
        # Output *before* the hang is the point: subprocess hands back a
        # timed-out child's partial output as bytes even under text=True,
        # and lirk once crashed joining that with str output.
        print("partial output before the hang", flush=True)
        sys.stderr.write("partial stderr before the hang\n")
        sys.stderr.flush()
        time.sleep(30)
