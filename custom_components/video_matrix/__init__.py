"""Set up and unload Video Matrix."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_MODEL, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_DRIVER
from .coordinator import MatrixCoordinator
from .drivers.base import MatrixDriver
from .drivers.registry import DRIVERS

PLATFORMS = [Platform.MEDIA_PLAYER]
type MatrixConfigEntry = ConfigEntry[MatrixCoordinator]


def create_driver(hass: HomeAssistant, data: dict) -> MatrixDriver:
    """Keep manufacturer selection outside the entity/coordinator layers."""
    registration = DRIVERS[data[CONF_DRIVER]]
    return registration.factory(
        async_get_clientsession(hass),
        data[CONF_HOST],
        data.get(CONF_PORT, registration.default_port),
        data[CONF_MODEL],
    )


async def async_setup_entry(hass: HomeAssistant, entry: MatrixConfigEntry) -> bool:
    coordinator = MatrixCoordinator(hass, entry, create_driver(hass, entry.data))
    entry.async_on_unload(coordinator.driver.async_close)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    return True


async def _async_update_options(hass: HomeAssistant, entry: MatrixConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: MatrixConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
