class IdempotencyStore:
    def __init__(self):
        self._records: dict[tuple[str, str], dict] = {}

    def lookup(self, tenant_id: str, key: str):
        return self._records.get((tenant_id, key))

    def store(self, tenant_id: str, key: str, response: dict):
        self._records[(tenant_id, key)] = response
