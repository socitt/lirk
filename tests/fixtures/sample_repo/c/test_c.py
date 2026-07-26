import unittest

from c import greet


class GreetTest(unittest.TestCase):
    def test_greet(self):
        self.assertEqual(greet(), "c")
