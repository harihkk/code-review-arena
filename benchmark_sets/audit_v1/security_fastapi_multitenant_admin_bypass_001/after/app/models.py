from dataclasses import dataclass


@dataclass
class User:
    id: int
    tenant_id: str
    role: str
