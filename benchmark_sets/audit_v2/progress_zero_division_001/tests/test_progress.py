from app.progress import percent_done


def test_half_finished():
    assert percent_done(5, 10) == 50.0


def test_none_finished():
    assert percent_done(0, 8) == 0.0


def test_all_finished():
    assert percent_done(8, 8) == 100.0


def test_empty_workload_is_complete():
    assert percent_done(0, 0) == 100.0
