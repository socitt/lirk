import unittest


class SecondTests(unittest.TestCase):
    def test_fails(self):
        self.assertTrue(False)


if __name__ == "__main__":
    unittest.main()
