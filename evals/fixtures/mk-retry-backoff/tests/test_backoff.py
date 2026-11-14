from lib.backoff import delay_for, schedule


def test_first_retry_waits_the_base_delay():
    assert delay_for(1) == 0.5


def test_schedule_has_one_delay_per_attempt():
    assert len(schedule(3)) == 3
