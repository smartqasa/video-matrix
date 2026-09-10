"""UI setup, connection reconfiguration, and input labels."""

import ipaddress
import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_MODEL, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from . import create_driver
from .const import CONF_DRIVER, CONF_SOURCE_NAMES, DOMAIN
from .drivers.base import MatrixConnectionError, MatrixProtocolError
from .drivers.registry import DRIVERS


def normalize_host(value: str) -> str:
    """Accept an address or DNS hostname, never a URL, path, or credentials."""
    host = value.strip().lower().rstrip(".")
    try:
        return ipaddress.ip_address(host).compressed
    except ValueError:
        if len(host) > 253 or not all(
            re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in host.split(".")
        ):
            raise ValueError("Enter only a hostname or IP address") from None
        return host


class MatrixConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Connect only after a validated read; configuration never switches routes."""

    VERSION = 1

    _driver: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> MatrixOptionsFlow:
        return MatrixOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._driver = user_input[CONF_DRIVER]
            return await self.async_step_connection()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DRIVER, default=next(iter(DRIVERS))): vol.In(
                        {key: driver.name for key, driver in DRIVERS.items()}
                    )
                }
            ),
        )

    async def async_step_connection(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self._connection_step("connection", user_input)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self._connection_step("reconfigure", user_input)

    def _address_configured(self, data: dict, entry: config_entries.ConfigEntry | None) -> bool:
        return any(
            existing.entry_id != (entry.entry_id if entry else None)
            and existing.data[CONF_HOST] == data[CONF_HOST]
            and existing.data[CONF_PORT] == data[CONF_PORT]
            for existing in self._async_current_entries()
        )

    async def _connection_step(self, step: str, user_input: dict | None) -> FlowResult:
        entry = self._get_reconfigure_entry() if step == "reconfigure" else None
        defaults = dict(entry.data) if entry else {}
        driver_key = entry.data[CONF_DRIVER] if entry else self._driver
        registration = DRIVERS[driver_key]
        errors = {}
        if user_input is not None:
            defaults.update(user_input)
            data = {**defaults, CONF_DRIVER: driver_key}
            if entry:
                # Reconfiguration changes the address, never the hardware profile/IDs.
                data[CONF_MODEL] = entry.data[CONF_MODEL]
            try:
                data[CONF_HOST] = normalize_host(data[CONF_HOST])
            except ValueError:
                errors[CONF_HOST] = "invalid_host"
            else:
                if self._address_configured(data, entry):
                    return self.async_abort(reason="already_configured")
                try:
                    driver = create_driver(self.hass, data)
                    try:
                        await driver.async_get_routes()
                    finally:
                        await driver.async_close()
                except MatrixConnectionError:
                    errors["base"] = "cannot_connect"
                except MatrixProtocolError:
                    errors["base"] = "invalid_response"
                else:
                    # Another flow can finish while this one awaits its status probe.
                    if self._address_configured(data, entry):
                        return self.async_abort(reason="already_configured")
                    if entry:
                        return self.async_update_reload_and_abort(entry, data_updates=data)
                    return self.async_create_entry(title=data[CONF_NAME], data=data)
        fields = {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(
                CONF_PORT, default=defaults.get(CONF_PORT, registration.default_port)
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
        }
        if not entry:
            fields[vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "Matrix"))] = vol.All(
                str, vol.Strip, vol.Length(min=1)
            )
            fields[
                vol.Required(
                    CONF_MODEL, default=defaults.get(CONF_MODEL, next(iter(registration.models)))
                )
            ] = vol.In(list(registration.models))
        return self.async_show_form(step_id=step, data_schema=vol.Schema(fields), errors=errors)


class MatrixOptionsFlow(config_entries.OptionsFlow):
    """Optional friendly source names, indexed by stable input number."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        registration = DRIVERS[self.config_entry.data[CONF_DRIVER]]
        count = registration.models[self.config_entry.data[CONF_MODEL]].input_count
        if user_input is not None:
            names = {
                str(index): user_input.get(f"input_{index}", "").strip()
                for index in range(1, count + 1)
            }
            return self.async_create_entry(title="", data={CONF_SOURCE_NAMES: names})
        current = self.config_entry.options.get(CONF_SOURCE_NAMES, {})
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(f"input_{index}", default=current.get(str(index), "")): str
                    for index in range(1, count + 1)
                }
            ),
        )
