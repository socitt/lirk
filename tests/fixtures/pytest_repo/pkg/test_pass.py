from greet import greet


def test_greet_uses_the_conftest_fixture(name):
    assert greet(name) == "hello, world"
