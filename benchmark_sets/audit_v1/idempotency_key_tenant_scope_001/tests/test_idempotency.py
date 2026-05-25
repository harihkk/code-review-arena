from app.idempotency import IdempotencyStore


def test_idempotency_keys_are_scoped_per_tenant():
    store = IdempotencyStore()
    store.store("tenant-a", "pay-1", {"status": "paid", "tenant": "tenant-a"})
    assert store.lookup("tenant-b", "pay-1") is None
