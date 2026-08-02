import unittest


class AfterTheHangTests(unittest.TestCase):
    def test_fails(self):
        # Deliberately fails, so a target pairing this with the hanging
        # src proves the src after a timeout was actually reached and
        # evaluated -- a passing test could not distinguish "ran" from
        # "skipped".
        self.fail("test_after.py is meant to fail")
