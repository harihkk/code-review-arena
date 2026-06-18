def net_charge(unit_price: int, count: int, pct_off: int) -> int:
    """Amount owed for ``count`` units at ``unit_price`` each after a percent reduction."""
    gross = unit_price * count
    reduction = gross * pct_off // 100
    return gross - reduction
