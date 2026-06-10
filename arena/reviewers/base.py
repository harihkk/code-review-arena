"""Reviewer protocol and shared behavior."""

from __future__ import annotations

from abc import ABC, abstractmethod

from arena.core.models import CaseContext, ReviewerResponse


class BaseReviewer(ABC):
    name: str
    model: str | None

    @abstractmethod
    def review(self, context: CaseContext) -> ReviewerResponse:
        """Review a case without receiving its ground-truth answer."""

    @property
    def identifier(self) -> str:
        return f"{self.name}:{self.model}" if self.model else self.name

    def safe_config(self) -> dict[str, object]:
        """Reviewer configuration safe to persist in run manifests (no secrets)."""
        return {}
