from dataclasses import dataclass

from app.events import OrderStatusChanged


@dataclass
class OrderState:
    status: str
    version: int


class OrderProjector:
    def __init__(self) -> None:
        self.state = OrderState(status="CREATED", version=0)

    def apply(self, event: OrderStatusChanged) -> OrderState:
        if event.version <= self.state.version:
            return self.state
        self.state.status = event.status
        self.state.version = event.version
        return self.state
