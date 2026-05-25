def cache_key(tenant_id: str, user_id: str, query: str) -> str:
    return f"search:{tenant_id}:{user_id}:{query}"


def search(redis, tenant_id: str, user_id: str, query: str, load):
    key = cache_key(tenant_id, user_id, query)
    cached = redis.get(key)
    if cached is not None:
        return cached
    result = load(tenant_id, user_id, query)
    redis.set(key, result)
    return result

