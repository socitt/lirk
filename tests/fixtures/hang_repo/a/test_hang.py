import time
import unittest


class HangTests(unittest.TestCase):
    def test_hangs(self):
        time.sleep(5)


if __name__ == "__main__":
    unittest.main()
