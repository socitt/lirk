import sys
import unittest


class StdinTests(unittest.TestCase):
    def test_stdin_is_closed_not_inherited(self):
        self.assertEqual(sys.stdin.readline(), "")


if __name__ == "__main__":
    unittest.main()
