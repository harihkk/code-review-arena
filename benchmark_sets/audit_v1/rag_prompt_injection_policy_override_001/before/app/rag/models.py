from dataclasses import dataclass


@dataclass
class RetrievedDocument:
    id: str
    text: str
