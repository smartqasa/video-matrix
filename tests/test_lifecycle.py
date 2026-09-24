"""Shutdown must quiesce active operations without accepting stale commands."""

import asyncio
import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from aiohttp import web
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.video_matrix import async_unload_entry
from custom_components.video_matrix.drivers.base import MatrixConnectionError
from custom_components.video_matrix.drivers.nohassle import parse_status


async def setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return {
        int(entity.unique_id.rsplit("_", 1)[1]): entity.entity_id
        for entity in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }


@pytest.mark.usefixtures("socket_enabled")
@pytest.mark.parametrize("cancel_active", [False, True])
async def test_service_unload_drains_io_rejects_queue_and_allows_new_setup(
    hass, entry, payload, aiohttp_server, cancel_active
):
    first_write = asyncio.Event()
    release_write = asyncio.Event()
    second_queued = asyncio.Event()
    unloading = asyncio.Event()
    requests = []
    writes = 0
    calls = 0

    async def handler(request):
        nonlocal writes
        command = json.loads(await request.text())
        requests.append(command)
        if command["comhead"] == "video switch":
            writes += 1
            source, output = command["source"]
            payload["allsource"][output - 1] = source
            if writes == 1:
                first_write.set()
                await release_write.wait()
            return web.json_response({"comhead": "video switch"})
        return web.json_response(payload)

    app = web.Application()
    app.router.add_post("/cgi-bin/instr", handler)
    server = await aiohttp_server(app)
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "host": server.host, "port": server.port}
    )
    entities = await setup(hass, entry)
    old_coordinator = entry.runtime_data
    session = old_coordinator.driver._session
    original_select = old_coordinator.async_select_source

    async def observe_select(output, source):
        nonlocal calls
        calls += 1
        if calls == 2:
            second_queued.set()
        await original_select(output, source)

    async def select(output, source):
        await hass.services.async_call(
            "media_player",
            "select_source",
            {"entity_id": entities[output], "source": source},
            blocking=True,
        )

    def state_changed():
        if entry.state is ConfigEntryState.UNLOAD_IN_PROGRESS:
            unloading.set()

    remove_listener = entry.async_on_state_change(state_changed)
    with patch.object(old_coordinator, "async_select_source", side_effect=observe_select):
        first = asyncio.create_task(select(1, "Roku 2"))
        await first_write.wait()
        second = asyncio.create_task(select(2, "Roku 4"))
        await second_queued.wait()
        unload = asyncio.create_task(hass.config_entries.async_unload(entry.entry_id))
        await unloading.wait()
        try:
            assert not unload.done()
            if cancel_active:
                first.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first
        finally:
            release_write.set()
            remove_listener()
        if not cancel_active:
            await first
        with pytest.raises(HomeAssistantError, match="unload"):
            await second
        assert await unload

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert [c for c in requests if c["comhead"] == "video switch"] == [
        {"comhead": "video switch", "source": [2, 1]}
    ]
    assert not session.closed
    count = len(requests)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(requests) == count

    # A fresh coordinator works after repeated setup, but an old reference must
    # remain unusable even when this same config entry is loaded again.
    for source in ("Roku 3", "Roku 2"):
        assert await setup(hass, entry) == entities
        assert entry.runtime_data.driver._session is session
        count = len(requests)
        with pytest.raises(HomeAssistantError, match="unload"):
            await old_coordinator.async_select_source(2, "Roku 4")
        assert len(requests) == count
        await select(1, source)
        assert hass.states.get(entities[1]).attributes["source"] == source
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert not session.closed


@pytest.mark.parametrize("failure", [False, RuntimeError("Unload failed")])
async def test_failed_platform_unload_keeps_driver_usable(hass, entry, driver, payload, failure):
    entry.add_to_hass(hass)
    await setup(hass, entry)
    coordinator = entry.runtime_data
    with patch.object(hass.config_entries, "async_unload_platforms") as unload_platforms:
        if isinstance(failure, Exception):
            unload_platforms.side_effect = failure
            with pytest.raises(RuntimeError, match="Unload failed"):
                await async_unload_entry(hass, entry)
        else:
            unload_platforms.return_value = False
            assert not await async_unload_entry(hass, entry)
    driver.async_close.assert_not_awaited()
    payload["allsource"][0] = 2
    driver.async_get_routes.return_value = parse_status(payload)
    await coordinator.async_select_source(1, "Roku 2")
    driver.async_select_source.assert_awaited_once_with(1, 2)
    assert await hass.config_entries.async_unload(entry.entry_id)
    driver.async_close.assert_awaited_once()


async def test_cancelled_shutdown_waiter_does_not_abandon_active_poll_cleanup(hass, entry, driver):
    entry.add_to_hass(hass)
    await setup(hass, entry)
    coordinator = entry.runtime_data
    reading = asyncio.Event()
    release_read = asyncio.Event()
    closed = asyncio.Event()
    snapshot = driver.async_get_routes.return_value

    async def read():
        reading.set()
        await release_read.wait()
        return snapshot

    driver.async_get_routes.side_effect = read
    driver.async_close.side_effect = closed.set
    poll = asyncio.create_task(coordinator.async_refresh())
    await reading.wait()
    shutdown = hass.async_create_task(coordinator.async_shutdown(), eager_start=True)
    driver.async_close.assert_not_awaited()
    shutdown.cancel()
    with pytest.raises(asyncio.CancelledError):
        await shutdown
    release_read.set()
    await poll
    await closed.wait()
    await coordinator.async_shutdown()
    driver.async_close.assert_awaited_once()
    with pytest.raises(HomeAssistantError, match="unload"):
        await coordinator.async_select_source(1, "Roku 2")
    await coordinator.async_refresh()
    assert driver.async_get_routes.await_count == 2  # Setup and the active poll only.
    assert await hass.config_entries.async_unload(entry.entry_id)
    driver.async_close.assert_awaited_once()


async def test_failed_driver_close_can_be_retried(hass, entry, driver):
    entry.add_to_hass(hass)
    await setup(hass, entry)
    coordinator = entry.runtime_data
    driver.async_close.side_effect = [MatrixConnectionError("Close interrupted"), None]
    with pytest.raises(MatrixConnectionError, match="Close interrupted"):
        await coordinator.async_shutdown()
    with pytest.raises(HomeAssistantError, match="unload"):
        await coordinator.async_select_source(1, "Roku 2")
    await coordinator.async_shutdown()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert driver.async_close.await_count == 2
