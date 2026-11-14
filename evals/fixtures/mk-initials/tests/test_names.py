from lib.names import initials


def test_initials_returns_a_string():
    assert isinstance(initials("Ada Lovelace"), str)
