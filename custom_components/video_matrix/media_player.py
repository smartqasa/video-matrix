"""Standard HA media players, one per independently routed matrix zone."""

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MatrixConfigEntry
from .const import DOMAIN
from .coordinator import MatrixCoordinator

PARALLEL_UPDATES = 0  # The shared coordinator serializes transactions across outputs.


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MatrixConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        MatrixOutput(entry, output)
        for output in range(1, entry.runtime_data.driver.identity.output_count + 1)
    )


class MatrixOutput(CoordinatorEntity[MatrixCoordinator], MediaPlayerEntity):
    """Route selection and confirmed feedback, without pretend playback/power controls."""

    _attr_has_entity_name = True
    _attr_supported_features = MediaPlayerEntityFeature.SELECT_SOURCE

    def __init__(self, entry: MatrixConfigEntry, output: int) -> None:
        super().__init__(entry.runtime_data)
        self._output = output
        self._attr_unique_id = f"{entry.entry_id}_output_{output}"
        identity = self.coordinator.driver.identity
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=identity.manufacturer,
            model=identity.model,
        )

    @property
    def name(self) -> str:
        return self.coordinator.data.output_names[self._output - 1]

    @property
    def state(self) -> MediaPlayerState | None:
        if not self.available:
            return None
        return MediaPlayerState.ON if self.coordinator.data.powered_on else MediaPlayerState.OFF

    @property
    def source_list(self) -> list[str]:
        return list(self.coordinator.sources)

    @property
    def source(self) -> str | None:
        if not self.available:
            return None
        source_id = self.coordinator.data.routes[self._output - 1]
        return self.coordinator.sources[source_id - 1]

    async def async_select_source(self, source: str) -> None:
        await self.coordinator.async_select_source(self._output, source)
