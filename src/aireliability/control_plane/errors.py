"""Exception types for the AI Reliability Engine control plane."""


class ControlPlaneError(Exception):
    """Base exception for all control-plane operations."""


class JobNotFoundError(ControlPlaneError):
    """Raised when a referenced job is not found in the queue or registry."""


class WorkerNotFoundError(ControlPlaneError):
    """Raised when a referenced worker is not registered in the worker manager."""


class WorkerCapacityExceededError(ControlPlaneError):
    """Raised when an assignment is attempted to a worker with zero free capacity."""


class InvalidJobStateError(ControlPlaneError):
    """Raised when an operation is invalid for the current queue or job state."""


class CancellationError(ControlPlaneError):
    """Raised when a cancellation request cannot be honored (e.g. already completed)."""
