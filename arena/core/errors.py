"""Domain exceptions used across the arena."""


class ArenaError(Exception):
    """Base exception for user-facing arena failures."""


class ValidationError(ArenaError):
    """Raised when a benchmark case is not internally consistent."""


class ReviewerError(ArenaError):
    """Raised when a reviewer cannot complete a requested review."""


class InvalidReviewerOutput(ReviewerError):
    """Raised when a model cannot produce a valid structured result."""


class StorageError(ArenaError):
    """Raised when the results database cannot be used safely."""
