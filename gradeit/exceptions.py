"""Exception hierarchy for gradeit.

All errors raised by the package derive from :class:`GradeitError`, so callers
can catch everything gradeit-specific with a single ``except GradeitError``.
The more specific errors also subclass the matching built-in (``ValueError`` /
``ImportError``) so existing ``except ValueError``/``except ImportError`` code
keeps working.
"""


class GradeitError(Exception):
    """Base class for all gradeit errors."""


class InvalidInputError(GradeitError, ValueError):
    """The coordinate input could not be interpreted (wrong type or shape)."""


class MissingDependencyError(GradeitError, ImportError):
    """An optional dependency (e.g. pandas, requests) is needed but not installed."""


class ElevationLookupError(GradeitError):
    """An elevation source failed to return a usable value."""
