def net_charge(unit_price: int, count: int, pct_off: int) -> int:
    """Amount owed for ``count`` units at ``unit_price`` each after a percent reduction."""
    unit_net = unit_price * (100 - pct_off) // 100
    return unit_net * count
