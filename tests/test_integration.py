"""Exercise actual HA setup, entities, services, polling, and unload."""

import asyncio
from dataclasses import replace
from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.video_matrix.coordinator import MatrixCoordinator, source_labels
from custom_components.video_matrix.drivers.base import MatrixConnectionError, MatrixIdentity
from custom_components.video_matrix.drivers.nohassle import parse_status


async def setup(hass, entry):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    entity_ids = {
        int(entity.unique_id.rsplit("_", 1)[1]): entity.entity_id
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    return entity_ids


async def select(hass, entity_id, source):
    await hass.services.async_call(
        "media_player", "select_source", {"entity_id": entity_id, "source": source}, blocking=True
    )


async def test_setup_standard_source_service_and_unload(hass, entry, driver, payload):
    entities = await setup(hass, entry)
    assert len(entities) == 8
    assert driver.async_get_routes.call_count == 1
    state = hass.states.get(entities[2])
    assert state.state == "on"
    assert state.attributes["source"] == "Roku 3"
    assert state.attributes["source_list"] == payload["allinputname"]
    payload["allsource"][0] = 2
    driver.async_get_routes.return_value = parse_status(payload)
    await select(hass, entities[1], "Roku 2")
    driver.async_select_source.assert_awaited_once_with(1, 2)
    assert hass.states.get(entities[1]).attributes["source"] == "Roku 2"
    assert driver.async_get_routes.call_count == 2
    assert await hass.config_entries.async_unload(entry.entry_id)
    driver.async_close.assert_awaited_once()
    assert entry.state is ConfigEntryState.NOT_LOADED
    count = driver.async_get_routes.call_count
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
    await hass.async_block_till_done()
    assert driver.async_get_routes.call_count == count


async def test_external_change_disconnect_recovery_and_power(hass, entry, driver, payload):
    entities = await setup(hass, entry)
    payload["allsource"][1] = 5
    driver.async_get_routes.return_value = parse_status(payload)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()
    assert hass.states.get(entities[2]).attributes["source"] == "Media Server"
    assert driver.async_get_routes.call_count == 2  # One poll, not eight polls.
    driver.async_get_routes.side_effect = MatrixConnectionError("Disconnected")
    await entry.runtime_data.async_refresh()
    assert all(hass.states.get(entity).state == "unavailable" for entity in entities.values())
    assert hass.states.get(entities[2]).attributes.get("source") is None
    driver.async_get_routes.side_effect = None
    payload["power"] = 0
    driver.async_get_routes.return_value = parse_status(payload)
    await entry.runtime_data.async_refresh()
    assert hass.states.get(entities[2]).state == "off"
    with pytest.raises(HomeAssistantError, match="powered off"):
        await select(hass, entities[1], "Roku 2")
    payload["power"] = 1
    driver.async_get_routes.return_value = parse_status(payload)
    await entry.runtime_data.async_refresh()
    assert hass.states.get(entities[2]).state == "on"
    assert hass.states.get(entities[2]).attributes["source"] == "Media Server"


async def test_no_optimistic_feedback_and_delayed_confirmation(hass, entry, driver, payload):
    entities = await setup(hass, entry)
    old = driver.async_get_routes.return_value
    payload["allsource"][0] = 2
    new = parse_status(payload)
    states_seen = []

    async def read():
        states_seen.append(hass.states.get(entities[1]).attributes["source"])
        return old if len(states_seen) == 1 else new

    driver.async_get_routes.side_effect = read
    await select(hass, entities[1], "Roku 2")
    assert states_seen == ["Roku 1", "Roku 1"]
    assert hass.states.get(entities[1]).attributes["source"] == "Roku 2"


async def test_unconfirmed_command_preserves_actual_route(hass, entry, driver):
    entities = await setup(hass, entry)
    with pytest.raises(HomeAssistantError, match="did not confirm"):
        await select(hass, entities[1], "Roku 2")
    assert hass.states.get(entities[1]).attributes["source"] == "Roku 1"
    assert hass.states.get(entities[1]).state == "on"
    driver.async_select_source.assert_awaited_once()


async def test_failed_write_reconciles_without_retry(hass, entry, driver, payload):
    entities = await setup(hass, entry)
    payload["allsource"][0] = 2
    driver.async_get_routes.return_value = parse_status(payload)
    driver.async_select_source.side_effect = MatrixConnectionError("Write timed out")
    with pytest.raises(HomeAssistantError, match="Write timed out"):
        await select(hass, entities[1], "Roku 2")
    driver.async_select_source.assert_awaited_once()
    assert hass.states.get(entities[1]).attributes["source"] == "Roku 2"


async def test_failed_confirmation_marks_unavailable(hass, entry, driver):
    entities = await setup(hass, entry)
    driver.async_get_routes.side_effect = MatrixConnectionError("Disconnected")
    with pytest.raises(HomeAssistantError, match="Disconnected"):
        await select(hass, entities[1], "Roku 2")
    assert hass.states.get(entities[1]).state == "unavailable"
    assert hass.states.get(entities[1]).attributes.get("source") is None
    with pytest.raises(HomeAssistantError, match="unavailable"):
        await entry.runtime_data.async_select_source(1, "Roku 2")
    driver.async_select_source.assert_awaited_once()


async def test_unknown_source_is_an_error(hass, entry, driver):
    entities = await setup(hass, entry)
    with pytest.raises(HomeAssistantError):
        await select(hass, entities[1], "Not an input")
    driver.async_select_source.assert_not_awaited()


async def test_unreachable_first_setup_retries(hass, entry, driver):
    entry.add_to_hass(hass)
    driver.async_get_routes.side_effect = MatrixConnectionError("Disconnected")
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert not hass.states.async_all("media_player")
    driver.async_close.assert_awaited_once()


async def test_cancelled_confirmation_marks_unavailable_and_releases_lock(hass, entry, driver):
    entities = await setup(hass, entry)
    reading = asyncio.Event()

    async def read():
        reading.set()
        await asyncio.Event().wait()

    driver.async_get_routes.side_effect = read
    task = asyncio.create_task(entry.runtime_data.async_select_source(1, "Roku 2"))
    await reading.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert hass.states.get(entities[1]).state == "unavailable"
    driver.async_get_routes.side_effect = None
    await entry.runtime_data.async_refresh()
    assert hass.states.get(entities[1]).state == "on"


async def test_commands_and_poll_are_serialized(hass, entry, driver, payload):
    coordinator = MatrixCoordinator(hass, entry, driver)
    coordinator.async_set_updated_data(parse_status(payload))
    events = []

    async def switch(output, source):
        events.append(f"write {output}")
        await asyncio.sleep(0)
        payload["allsource"][output - 1] = source

    async def read():
        events.append("read")
        await asyncio.sleep(0)
        return parse_status(payload)

    driver.async_select_source.side_effect = switch
    driver.async_get_routes.side_effect = read
    await asyncio.gather(
        coordinator.async_select_source(1, "Roku 2"),
        coordinator.async_select_source(2, "Roku 4"),
        coordinator.async_refresh(),
    )
    assert events == ["write 1", "read", "write 2", "read", "read"]
    assert coordinator.data.routes[:2] == (2, 4)
    await coordinator.async_shutdown()


async def test_ids_survive_labels_and_connection_reload(hass, entry, driver, payload):
    entities = await setup(hass, entry)
    payload["alloutputname"][0] = "Renamed Room"
    driver.async_get_routes.return_value = parse_status(payload)
    hass.config_entries.async_update_entry(entry, data={**entry.data, "host": "new-matrix.test"})
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    assert registry.async_get(entities[1]).unique_id == f"{entry.entry_id}_output_1"
    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 8


async def test_other_brand_and_zone_counts_use_same_entities(hass, entry, driver, payload):
    """A synthetic 2x3 driver proves the HA layer has no No Hassle assumptions."""
    driver.identity = MatrixIdentity("Example Brand", "Test 2x3", 2, 3)
    driver.async_get_routes.return_value = replace(
        parse_status(payload),
        routes=(1, 2, 1),
        input_names=("A", "B"),
        output_names=("X", "Y", "Z"),
    )
    entities = await setup(hass, entry)
    assert len(entities) == 3
    assert hass.states.get(entities[2]).attributes["source"] == "B"
    driver.async_get_routes.return_value = replace(
        driver.async_get_routes.return_value, routes=(2, 2, 1)
    )
    await select(hass, entities[1], "B")
    driver.async_select_source.assert_awaited_once_with(1, 2)


def test_source_names_are_unique_and_ids_are_retained():
    names = ("Roku", "Roku", "Roku (Input 1)", "", "Input 4")
    labels = source_labels(names, {})
    assert len(set(labels)) == 5
    assert labels[2] == "Roku (Input 1)"
    assert source_labels(("Vendor A", "Vendor B"), {"2": "My source"}) == ("Vendor A", "My source")
