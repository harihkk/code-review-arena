from app.pricing import net_charge


def test_known_charge_values():
    # 3 units at 10 each, 33 percent off: the reduction on the full amount is 9.
    assert net_charge(10, 3, 33) == 21


def test_zero_units_owes_nothing():
    assert net_charge(100, 0, 20) == 0


def test_no_reduction_charges_full():
    assert net_charge(250, 4, 0) == 1000


def test_charge_consistent_across_quantities():
    # Reducing the full amount must not depend on how it is split per unit.
    for count in range(1, 6):
        gross = 10 * count
        expected = gross - (gross * 33 // 100)
        assert net_charge(10, count, 33) == expected
