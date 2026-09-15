"""Exception types.

One base class so a caller can write ``except SwmcError`` and be done.

``UnknownTypeError`` also inherits ``KeyError`` because looking a component type
up by name really is a mapping lookup, and code written around
``COMPONENT_TYPES[...]`` should keep working.
"""

from __future__ import annotations

__all__ = ["SwmcError", "EditError", "UnknownTypeError"]


class SwmcError(Exception):
    """Base class for every error this library raises."""


class EditError(SwmcError):
    """An edit was rejected because it would produce an invalid document."""


class UnknownTypeError(EditError, KeyError):
    """A component type could not be resolved from an id, alias or name."""

    def __str__(self) -> str:
        # KeyError.__str__ reprs its argument, which turns a helpful sentence
        # into a quoted blob.
        return self.args[0] if self.args else ""
