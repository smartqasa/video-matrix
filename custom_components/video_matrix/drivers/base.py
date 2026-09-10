"""Manufacturer-independent matrix contract. No Home Assistant dependencies."""

from dataclasses import dataclass
from typing import Protocol


class MatrixError(Exception):
    """Base error for a failed matrix operation."""


class MatrixConnectionError(MatrixError):
    """Device could not be reached or returned an HTTP error."""


class MatrixProtocolError(MatrixError):
    """Device returned incomplete or unsupported status."""


class MatrixCommandError(MatrixError):
    """The requested route was not confirmed."""


@dataclass(frozen=True)
class MatrixIdentity:
    """Known device identity and capabilities, independent of physical sockets."""

    manufacturer: str
    model: str
    input_count: int
    output_count: int


@dataclass(frozen=True)
class RoutingSnapshot:
    """Complete immutable state; tuple position + 1 is the numeric channel ID."""

    routes: tuple[int, ...]
    input_names: tuple[str, ...]
    output_names: tuple[str, ...]
    powered_on: bool


class MatrixDriver(Protocol):
    """Implement this interface for future tested matrix protocols.

    Reads return complete snapshots or raise MatrixError. Writes send one command;
    the coordinator performs read-back confirmation. I/O must be serialized.
    """

    @property
    def identity(self) -> MatrixIdentity:
        """Return model capabilities."""
        ...

    async def async_get_routes(self) -> RoutingSnapshot:
        """Read actual routing and power state."""
        ...

    async def async_select_source(self, output: int, source: int) -> None:
        """Request a route using one-based numeric IDs, or raise MatrixError."""
        ...

    async def async_close(self) -> None:
        """Release driver-owned connections; never close an injected shared session."""
        ...
