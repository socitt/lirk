# Skips itself when an optional package is missing -- the standard way
# to make a test module optional. Must PASS under lirk, not read as
# "contained no tests" (found by the slingshot repo).
import pytest

np = pytest.importorskip("a_package_that_is_never_installed_xyz")


def test_uses_it():
    assert np
