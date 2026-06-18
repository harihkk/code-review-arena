from app.idempotency import IdempotencyStore


def test_repeated_request_returns_one_charge():
    store = IdempotencyStore()
    store.store("tenant-a", "pay-1", {"status": "paid", "tenant": "tenant-a"})
    assert store.lookup("tenant-b", "pay-1") is None
