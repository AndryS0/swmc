"""swmc -- read, edit and serve Stormworks microprocessor XML files.

The component tables in :mod:`swmc.nodetypes` were reverse engineered from
``stormworks64.exe``; see ``README.md`` for the addresses they came from.
"""

from .model import Component, EditError, Microprocessor, fmt_num
from .nodetypes import (
    BRIDGE_TYPES,
    CATEGORY,
    COMPONENT_TYPES,
    DATA_TYPE,
    DATA_TYPE_SHORT,
    ComponentType,
    find_type,
)

__version__ = "1.0.0"

__all__ = [
    "Microprocessor",
    "Component",
    "EditError",
    "fmt_num",
    "COMPONENT_TYPES",
    "BRIDGE_TYPES",
    "CATEGORY",
    "DATA_TYPE",
    "DATA_TYPE_SHORT",
    "ComponentType",
    "find_type",
]
