"""Automatic HA recovery through the real HTTP driver and scheduled timers."""

import json
from datetime import timedelta

import pytest
from aiohttp import web
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed


async def advance(hass, freezer, seconds):
    """Fire already-scheduled HA timers, without requesting a manual refresh."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)


def assert_sources(hass, entry, payload):
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert len(entities) == 8
    for entity in entities:
        output = int(entity.unique_id.rsplit("_", 1)[1])
        state = hass.states.get(entity.entity_id)
        assert state.state == "on"
        assert (
            state.attributes["source"]
            == payload["allinputname"][payload["allsource"][output - 1] - 1]
        )
    return entities


@pytest.fixture
async def matrix_server(hass, entry, payload, aiohttp_server):
    """Allow real connection loss or an incomplete device startup response."""
    state = {"partial": False, "requests": []}

    async def handler(request):
        command = json.loads(await request.text())
        state["requests"].append(command)
        assert command == {"comhead": "get video status"}
        if state["partial"]:
            return web.json_response({"comhead": "get video status", "power": 1})
        return web.json_response(payload)

    def app():
        application = web.Application()
        application.router.add_post("/cgi-bin/instr", handler)
        return application

    server = await aiohttp_server(app())
    port = server.port
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "host": server.host, "port": port}
    )

    async def disconnect(failure):
        if failure == "connection_refused":
            await server.close()
        else:
            state["partial"] = True

    async def reconnect(failure):
        if failure == "connection_refused":
            await aiohttp_server(app(), port=port)
        else:
            state["partial"] = False

    return disconnect, reconnect, state["requests"]


@pytest.mark.freeze_time(real_asyncio=True)
@pytest.mark.usefixtures("socket_enabled")
@pytest.mark.parametrize("failure", ["connection_refused", "partial"])
@pytest.mark.parametrize("changed_route", [False, True])
async def test_scheduled_poll_recovers_with_same_or_changed_routes(
    hass, entry, payload, matrix_server, freezer, failure, changed_route
):
    disconnect, reconnect, requests = matrix_server
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    entities = assert_sources(hass, entry, payload)
    await disconnect(failure)
    for _ in range(2):
        await advance(hass, freezer, 12)
        assert all(hass.states.get(e.entity_id).state == "unavailable" for e in entities)
        assert all(hass.states.get(e.entity_id).attributes.get("source") is None for e in entities)
    if changed_route:
        payload["allsource"][0] = 2
    await reconnect(failure)
    await advance(hass, freezer, 12)
    assert entry.runtime_data is coordinator
    assert_sources(hass, entry, payload)
    count = len(requests)
    await advance(hass, freezer, 12)
    assert len(requests) == count + 1
    assert_sources(hass, entry, payload)
    assert await hass.config_entries.async_unload(entry.entry_id)
    count = len(requests)
    await advance(hass, freezer, 30)
    assert len(requests) == count
    assert not async_get_clientsession(hass).closed


@pytest.mark.freeze_time(real_asyncio=True)
@pytest.mark.usefixtures("socket_enabled")
@pytest.mark.parametrize("failure", ["connection_refused", "partial"])
async def test_offline_startup_retries_setup_then_starts_normal_polling(
    hass, entry, payload, matrix_server, freezer, failure
):
    disconnect, reconnect, requests = matrix_server
    session = async_get_clientsession(hass)
    await disconnect(failure)
    hass.set_state(CoreState.starting)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert not hass.states.async_all("media_player")
    assert not session.closed

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    await advance(hass, freezer, 12)
    assert entry.state is ConfigEntryState.SETUP_RETRY

    await reconnect(failure)
    # Reachability alone does not bypass a pending setup-retry timer.
    await advance(hass, freezer, 5)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    await advance(hass, freezer, 17)
    assert entry.state is ConfigEntryState.LOADED
    assert_sources(hass, entry, payload)
    assert not session.closed

    payload["allsource"][0] = 2
    await advance(hass, freezer, 12)
    assert_sources(hass, entry, payload)
    assert await hass.config_entries.async_unload(entry.entry_id)
    count = len(requests)
    await advance(hass, freezer, 30)
    assert len(requests) == count
    assert not session.closed
