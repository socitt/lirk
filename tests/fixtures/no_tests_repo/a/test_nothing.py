"""Valid Python, imports unittest, defines no TestCase.

`python3 -m unittest test_nothing` exits 5 on 3.12+ but 0 on 3.11, so
an exit-code-only check reports a false PASS on a supported runtime.
"""

import unittest  # noqa: F401


def not_a_test():
    return "this is never collected"
