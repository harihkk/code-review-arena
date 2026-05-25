from dataclasses import dataclass


@dataclass
class User:
    id: str
    organization_id: str


@dataclass
class Document:
    id: str
    organization_id: str
    title: str
