from dataclasses import dataclass


@dataclass
class Record:
    id: str
    created_at: int
    label: str
