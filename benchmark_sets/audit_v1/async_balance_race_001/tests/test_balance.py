import asyncio

from app.balance import BalanceService


def test_parallel_updates_do_not_lose_writes():
    async def scenario():
        service = BalanceService()
        await asyncio.gather(service.add(10), service.add(20))
        return service.balance

    assert asyncio.run(scenario()) == 30
