"""Timeout errors for execution tooling."""


class ExecutionTimeout(RuntimeError):
    """A benchmark helper command exceeded its configured limit."""
