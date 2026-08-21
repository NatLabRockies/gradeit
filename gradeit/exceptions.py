"""Exception and warning hierarchy for gradeit.

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


class GradeitWarning(UserWarning):
    """Base class for all gradeit warnings.

    Warnings are not errors, so this deliberately does not derive from
    :class:`GradeitError`. Silence a category with
    ``warnings.simplefilter("ignore", GradeitWarning)``, or turn it into an
    error with ``warnings.simplefilter("error", GradeitWarning)``.
    """


class SparseGridWarning(GradeitWarning):
    """A filter's distance grid is finer than the GPS points can support.

    Raised by :class:`~gradeit.filters.Wood2014Filter` when most of its uniform
    distance grid falls between GPS points, so the profile it filters is mostly
    interpolation rather than measurement.
    """
