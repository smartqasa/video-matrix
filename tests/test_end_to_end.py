"""Full HTTP driver to HA entity/service path against a simulated matrix."""

import json

import pytest
from aiohttp import web
from homeassistant.helpers import entity_registry as er


@pytest.mark.usefixtures("socket_enabled")
@pytest.mark.parametrize("stale_acknowledgements", [0, 2])
async def test_real_driver_setup_switch_feedback_and_unload(
    hass, entry, payload, aiohttp_server, stale_acknowledgements
):
    commands = []
    pending_acknowledgements = 0

    async def handler(request):
        nonlocal pending_acknowledgements
        command = json.loads(await request.text())
        commands.append(command)
        if command["comhead"] == "video switch":
            source, output = command["source"]
            payload["allsource"][output - 1] = source
            pending_acknowledgements = stale_acknowledgements
            return web.Response(text="")
        if pending_acknowledgements:
            pending_acknowledgements -= 1
            # NHAV-8X16V5 returns this write acknowledgement to status requests
            # while settling. It has no routing snapshot and must never be used.
            return web.json_response({"comhead": "video switch"})
        return web.json_response(payload)

    app = web.Application()
    app.router.add_post("/cgi-bin/instr", handler)
    server = await aiohttp_server(app)
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "host": server.host, "port": server.port}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert len(entities) == 8
    entity = next(item for item in entities if item.unique_id.endswith("_output_1"))
    assert hass.states.get(entity.entity_id).attributes["source"] == "Roku 1"
    await hass.services.async_call(
        "media_player",
        "select_source",
        {"entity_id": entity.entity_id, "source": "Roku 2"},
        blocking=True,
    )
    assert hass.states.get(entity.entity_id).attributes["source"] == "Roku 2"
    assert commands == [
        {"comhead": "get video status"},
        {"comhead": "video switch", "source": [2, 1]},
    ] + [{"comhead": "get video status"}] * (1 + stale_acknowledgements)
    assert await hass.config_entries.async_unload(entry.entry_id)
