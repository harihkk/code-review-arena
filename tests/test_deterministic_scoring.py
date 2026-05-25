from arena.scoring.metrics import f_beta_score, precision, rate, recall


def test_precision_recall_and_f_scores():
    assert precision(3, 1) == 0.75
    assert recall(3, 2) == 0.6
    assert round(f_beta_score(0.75, 0.6), 4) == 0.6667
    assert round(f_beta_score(0.75, 0.6, 0.5), 4) == 0.7143


def test_safe_rates_for_zero_denominators():
    assert precision(0, 0) == 0
    assert recall(0, 0) == 0
    assert rate(0, 0) is None
