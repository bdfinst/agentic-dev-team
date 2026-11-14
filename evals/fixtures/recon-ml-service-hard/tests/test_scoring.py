from app.domain.scoring import band


def test_band_thresholds():
    assert band(0.85) == "high"
    assert band(0.5) == "medium"
    assert band(0.1) == "low"
