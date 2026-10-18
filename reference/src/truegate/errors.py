class WorkbenchError(ValueError):
    """A user-correctable data or workflow problem."""


class Conflict(WorkbenchError):
    """The requested operation conflicts with recorded state."""

