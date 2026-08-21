"""Exception and warning hierarchy for gradeit.

All package errors inherit from :class:`GradeitError`. Specific errors also
inherit from the matching built-in error type.
"""


class GradeitError(Exception):
    """Base class for all gradeit errors."""


class InvalidInputError(GradeitError, ValueError):
    """The coordinate input could not be interpreted (wrong type or shape)."""


class MissingDependencyError(GradeitError, ImportError):
    """An optional dependency (e.g. pandas, requests) is needed but not installed."""


class ElevationLookupError(GradeitError):
    """An elevation source failed to return a usable value."""


class GradeitWarning(UserWarning):
    """Base class for all gradeit warnings.

    Warnings do not inherit from :class:`GradeitError`.
    """


class SparseGridWarning(GradeitWarning):
    """A filter's distance grid is finer than the GPS points can support.

    This warning is raised when most filter grid nodes have no GPS point.
    """
