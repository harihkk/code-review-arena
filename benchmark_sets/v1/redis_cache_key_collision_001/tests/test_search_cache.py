from app.search_cache import search


class Redis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value


def test_results_do_not_cross_tenants():
    redis = Redis()
    loader = lambda tenant, user, query: f"{tenant}:{query}"
    assert search(redis, "north", "7", "open", loader) == "north:open"
    assert search(redis, "south", "7", "private", loader) == "south:private"

