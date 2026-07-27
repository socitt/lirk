import unittest


class IndepTests(unittest.TestCase):
    def test_trivially_passes(self):
        self.assertEqual(1 + 1, 2)


if __name__ == "__main__":
    unittest.main()
