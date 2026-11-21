import pytest


@pytest.fixture
def name():
    # Supplied by conftest, not the test module, so a passing test
    # proves pytest really loaded this file.
    return "world"
