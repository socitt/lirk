import unittest

from b import greet


class GreetTest(unittest.TestCase):
    def test_greet(self):
        self.assertEqual(greet(), "b")
