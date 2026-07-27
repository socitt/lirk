import unittest

from pkg.thing import value


class ValueTests(unittest.TestCase):
    def test_value_is_42(self):
        self.assertEqual(value(), 42)


if __name__ == "__main__":
    unittest.main()
