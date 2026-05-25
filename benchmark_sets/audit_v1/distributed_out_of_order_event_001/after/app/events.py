from dataclasses import dataclass


@dataclass
class OrderStatusChanged:
    order_id: str
    version: int
    status: str
