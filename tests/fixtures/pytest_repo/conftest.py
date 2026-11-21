import pytest


@pytest.fixture
def punctuation():
    # Defined at the repo root, above the package: pytest only sees it if
    # lirk runs pytest with the repo root as its rootdir/confcutdir.
    return "!"
