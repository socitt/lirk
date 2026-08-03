import unittest

from base.base import VALUE


class UndeclaredTests(unittest.TestCase):
    def test_value(self):
        self.assertEqual(VALUE, 1)
