class IdempotencyStore:
    def __init__(self):
        self._records: dict[str, dict] = {}

    def lookup(self, tenant_id: str, key: str):
        return self._records.get(key)

    def store(self, tenant_id: str, key: str, response: dict):
        self._records[key] = response
