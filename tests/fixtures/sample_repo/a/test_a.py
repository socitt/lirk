import unittest

from a import greet


class GreetTest(unittest.TestCase):
    def test_greet(self):
        self.assertEqual(greet(), "a")
