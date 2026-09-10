"""Home Assistant fixtures; no household or hardware connections."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.video_matrix.const import DOMAIN
from custom_components.video_matrix.drivers.nohassle import NHAV_8X16V5, parse_status


@pytest.fixture(autouse=True)
def enable_custom_integration(enable_custom_integrations):
    yield


@pytest.fixture
def payload():
    return json.loads((Path(__file__).parent / "fixtures/video_status.json").read_text())


@pytest.fixture
def entry():
    return MockConfigEntry(
        domain=DOMAIN,
        title="Matrix",
        data={
            "host": "matrix.test",
            "port": 80,
            "name": "Matrix",
            "driver": "nohassle",
            "model": "NHAV-8X16V5",
        },
    )


@pytest.fixture
def driver(payload):
    driver = AsyncMock()
    driver.identity = NHAV_8X16V5
    driver.async_get_routes.return_value = parse_status(payload)
    with (
        patch("custom_components.video_matrix.create_driver", return_value=driver),
        patch("custom_components.video_matrix.config_flow.create_driver", return_value=driver),
        patch("custom_components.video_matrix.coordinator.CONFIRM_DELAY", 0),
    ):
        yield driver
