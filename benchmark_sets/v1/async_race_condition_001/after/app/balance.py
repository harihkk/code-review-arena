import asyncio


class BalanceService:
    def __init__(self):
        self.balance = 0

    async def add(self, amount: int) -> None:
        current = self.balance
        await asyncio.sleep(0)
        self.balance = current + amount

