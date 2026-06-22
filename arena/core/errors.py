"""Domain exceptions used across the arena."""


class ArenaError(Exception):
    """Base exception for user-facing arena failures."""


class ValidationError(ArenaError):
    """Raised when a benchmark case is not internally consistent."""


class InputTooLargeError(ValidationError):
    """Externally controlled input exceeded its pre-parse byte limit."""


class UnsafeInputError(ValidationError):
    """An input artifact is a symlink, special file, or otherwise unsafe to read."""


class InvalidEncodingError(ValidationError):
    """Externally controlled input is not valid UTF-8."""


class ReviewerError(ArenaError):
    """Raised when a reviewer cannot complete a requested review."""


class InvalidReviewerOutput(ReviewerError):
    """Raised when a model cannot produce a valid structured result."""


class StorageError(ArenaError):
    """Raised when the results database cannot be used safely."""


class ExecutionError(ArenaError):
    """Raised when a pack-controlled command cannot be run safely."""
