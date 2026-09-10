"""Setup validation, source-name options, and stable address reconfiguration."""

import asyncio
from unittest.mock import patch

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.video_matrix.config_flow import normalize_host
from custom_components.video_matrix.const import DOMAIN
from custom_components.video_matrix.drivers.base import (
    MatrixConnectionError,
    MatrixProtocolError,
)


async def start(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"driver": "nohassle"})


async def test_user_flow_probes_without_switching(hass, driver, entry):
    result = await start(hass)
    assert result["step_id"] == "connection"
    with patch("custom_components.video_matrix.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {k: v for k, v in entry.data.items() if k != "driver"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == "matrix.test"
    driver.async_select_source.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (MatrixConnectionError("Timeout"), "cannot_connect"),
        (MatrixProtocolError("Missing allsource"), "invalid_response"),
    ],
)
async def test_flow_errors_then_retry(hass, driver, entry, error, key):
    result = await start(hass)
    driver.async_get_routes.side_effect = error
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {k: v for k, v in entry.data.items() if k != "driver"}
    )
    assert result["errors"] == {"base": key}
    driver.async_get_routes.side_effect = None
    with patch("custom_components.video_matrix.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {k: v for k, v in entry.data.items() if k != "driver"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_address_and_invalid_host(hass, driver, entry):
    entry.add_to_hass(hass)
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {**{k: v for k, v in entry.data.items() if k != "driver"}, "host": "http://matrix.test/"},
    )
    assert result["errors"] == {"host": "invalid_host"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {**{k: v for k, v in entry.data.items() if k != "driver"}, "host": " MATRIX.TEST. "},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    driver.async_get_routes.assert_not_awaited()


async def test_reconfigure_preserves_entry_identity(hass, driver, entry):
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    with patch("homeassistant.config_entries.ConfigEntries.async_reload", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "new-matrix.test", "port": 8080}
        )
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == "new-matrix.test"
    assert entry.data["model"] == "NHAV-8X16V5"


async def test_options_maps_friendly_names_to_input_ids(hass, driver, entry):
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"input_1": " My Roku ", "input_2": ""}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["source_names"]["1"] == "My Roku"
    assert entry.options["source_names"]["2"] == ""


async def test_concurrent_setup_cannot_create_duplicate_entries(hass, driver, entry):
    first, second = await start(hass), await start(hass)
    started = asyncio.Event()
    release = asyncio.Event()
    snapshot = driver.async_get_routes.return_value

    async def probe():
        started.set()
        await release.wait()
        return snapshot

    driver.async_get_routes.side_effect = probe
    data = {key: value for key, value in entry.data.items() if key != "driver"}
    with patch("custom_components.video_matrix.async_setup_entry", return_value=True):
        pending = asyncio.create_task(
            hass.config_entries.flow.async_configure(first["flow_id"], data)
        )
        await started.wait()
        driver.async_get_routes.side_effect = None
        result = await hass.config_entries.flow.async_configure(second["flow_id"], data)
        assert result["type"] is FlowResultType.CREATE_ENTRY
        release.set()
        duplicate = await pending
        await hass.async_block_till_done()
    assert duplicate["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


@pytest.mark.parametrize("host", ["example.test", "192.0.2.10", "2001:db8::1"])
def test_valid_addresses(host):
    assert normalize_host(host) == host


@pytest.mark.parametrize("host", ["", "a/b", "a:80", "user@a", "-host", "host_", "https://a"])
def test_invalid_addresses(host):
    with pytest.raises(ValueError):
        normalize_host(host)
