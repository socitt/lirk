import unittest


class FailingDupTests(unittest.TestCase):
    def test_fails(self):
        self.fail("one/test_dup.py is meant to fail")
