import pytest
from lib.backoff import delay_for, schedule


def test_later_retries_wait_longer():
    assert delay_for(3) > delay_for(2)


def test_attempt_zero_is_rejected():
    with pytest.raises(ValueError):
        delay_for(0)


def test_schedule_of_no_retries_is_empty():
    assert schedule(0) == []
