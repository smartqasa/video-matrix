"""Shared polling and serialized, confirmed routing commands."""

import asyncio
import logging
from collections import Counter
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_SOURCE_NAMES, DEFAULT_POLL_INTERVAL, DOMAIN
from .drivers.base import MatrixCommandError, MatrixDriver, MatrixError, RoutingSnapshot

_LOGGER = logging.getLogger(__name__)
CONFIRM_ATTEMPTS = 3
CONFIRM_DELAY = 0.5


def source_labels(names: tuple[str, ...], overrides: dict[str, str]) -> tuple[str, ...]:
    """Map numeric IDs to unambiguous HA source strings, even with duplicate labels."""
    labels = [overrides.get(str(i), "") or name or f"Input {i}" for i, name in enumerate(names, 1)]
    counts = Counter(labels)
    used: set[str] = set()
    result = []
    for index, label in enumerate(labels, 1):
        candidate = label if counts[label] == 1 else f"{label} (Input {index})"
        while candidate in used or (candidate != label and candidate in counts):
            candidate += f" (Input {index})"
        used.add(candidate)
        result.append(candidate)
    return tuple(result)


class MatrixCoordinator(DataUpdateCoordinator[RoutingSnapshot]):
    """Publish only complete, device-reported snapshots for every output."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, driver: MatrixDriver) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=DEFAULT_POLL_INTERVAL),
            always_update=False,
        )
        self.driver = driver
        self._transaction_lock = asyncio.Lock()
        self._source_overrides = entry.options.get(CONF_SOURCE_NAMES, {})

    @property
    def sources(self) -> tuple[str, ...]:
        return source_labels(self.data.input_names, self._source_overrides)

    async def _async_update_data(self) -> RoutingSnapshot:
        async with self._transaction_lock:
            try:
                return await self.driver.async_get_routes()
            except MatrixError as err:
                raise UpdateFailed(str(err)) from err

    async def _read_after_write(self, expected: tuple[int, int] | None = None) -> None:
        """Retry bounded status reads; never resend a write or publish an acknowledgement."""
        for attempt in range(CONFIRM_ATTEMPTS):
            try:
                snapshot = await self.driver.async_get_routes()
            except MatrixError as err:
                _LOGGER.debug(
                    "Status read after routing failed (%s/%s): %s",
                    attempt + 1,
                    CONFIRM_ATTEMPTS,
                    err,
                )
                if attempt == CONFIRM_ATTEMPTS - 1:
                    self.async_set_update_error(UpdateFailed(str(err)))
                    raise
            else:
                self.async_set_updated_data(snapshot)
                if expected is None:
                    return
                output, source = expected
                if snapshot.powered_on and snapshot.routes[output - 1] == source:
                    return
                if attempt == CONFIRM_ATTEMPTS - 1:
                    raise MatrixCommandError(
                        f"Matrix did not confirm input {source} on output {output}"
                    )
            await asyncio.sleep(CONFIRM_DELAY)

    async def async_select_source(self, output: int, source_name: str) -> None:
        """Serialize the whole write/read-back transaction against commands and polls."""
        async with self._transaction_lock:
            if not self.last_update_success:
                raise HomeAssistantError(
                    "Matrix is unavailable; wait for a successful status update"
                )
            try:
                source = self.sources.index(source_name) + 1
            except ValueError as err:
                raise HomeAssistantError(f"Unknown matrix source: {source_name}") from err
            if not self.data.powered_on:
                raise HomeAssistantError("Matrix is powered off")
            try:
                try:
                    await self.driver.async_select_source(output, source)
                except MatrixError as write_error:
                    # A timed-out write may have reached the hardware. Reconcile,
                    # but never blindly resend or report that write as successful.
                    try:
                        await self._read_after_write()
                    except MatrixError as read_error:
                        raise MatrixCommandError(
                            f"Routing write failed: {write_error}; "
                            f"status reconciliation also failed: {read_error}"
                        ) from write_error
                    raise
                await self._read_after_write((output, source))
            except MatrixError as err:
                raise HomeAssistantError(str(err)) from err
            except asyncio.CancelledError:
                # Cancellation can happen after a write; old feedback is no longer reliable.
                self.async_set_update_error(UpdateFailed("Routing confirmation was interrupted"))
                raise
