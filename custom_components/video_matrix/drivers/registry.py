"""Supported profiles and factories. Register future brands here."""

from collections.abc import Callable
from dataclasses import dataclass

from aiohttp import ClientSession

from .base import MatrixDriver, MatrixIdentity
from .nohassle import NHAV_8X16V5, NoHassleDriver


@dataclass(frozen=True)
class DriverRegistration:
    """Transport factory and explicitly supported models for a manufacturer."""

    name: str
    models: dict[str, MatrixIdentity]
    default_port: int
    factory: Callable[[ClientSession, str, int, str], MatrixDriver]


DRIVERS = {
    "nohassle": DriverRegistration(
        name="No Hassle AV",
        models={NHAV_8X16V5.model: NHAV_8X16V5},
        default_port=80,
        factory=NoHassleDriver,
    ),
}
