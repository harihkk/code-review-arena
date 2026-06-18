from app.eligibility import is_eligible


def test_requires_both_conditions():
    assert is_eligible(20, has_consent=True) is True


def test_old_enough_without_consent_is_refused():
    assert is_eligible(20, has_consent=False) is False


def test_consenting_while_underage_is_refused():
    assert is_eligible(16, has_consent=True) is False
