import asyncio


class BalanceService:
    def __init__(self):
        self.balance = 0
        self.lock = asyncio.Lock()

    async def add(self, amount: int) -> None:
        async with self.lock:
            current = self.balance
            await asyncio.sleep(0)
            self.balance = current + amount
