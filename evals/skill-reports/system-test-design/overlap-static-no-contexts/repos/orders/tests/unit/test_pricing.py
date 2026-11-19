from src.pricing import apply_discount


def test_discount():
    assert apply_discount(100, 'gold') == 90
