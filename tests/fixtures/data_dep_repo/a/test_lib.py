import unittest

from lib import read_story


class ReadStoryTests(unittest.TestCase):
    def test_story_contents(self):
        self.assertEqual(
            read_story(), "You are in a maze of twisty passages."
        )


if __name__ == "__main__":
    unittest.main()
