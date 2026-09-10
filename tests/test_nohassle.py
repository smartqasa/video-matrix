"""Protocol regressions and real HTTP transport tests against a local fake device."""

import asyncio
import json

import aiohttp
import pytest
from aiohttp import web

from custom_components.video_matrix.drivers.base import (
    MatrixCommandError,
    MatrixConnectionError,
    MatrixProtocolError,
)
from custom_components.video_matrix.drivers.nohassle import NoHassleDriver, parse_status


def test_eight_zones_and_integer_strings(payload):
    snapshot = parse_status(payload)
    assert snapshot.routes == (1, 3, 1, 4, 5, 6, 7, 8)
    assert len(snapshot.output_names) == 8
    payload["allsource"] = [str(value) for value in snapshot.routes]
    payload["power"] = "0"
    assert parse_status(payload).powered_on is False
    assert parse_status(payload).routes == snapshot.routes


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("comhead", "get status"),
        ("allsource", None),
        ("allsource", [1] * 7),
        ("allsource", [1] * 9),
        ("allsource", [1] * 8 + [0, 0]),
        ("allsource", [0] + [1] * 7),
        ("allsource", [9] + [1] * 7),
        ("allsource", [True] + [1] * 7),
        ("allsource", [1.5] + [1] * 7),
        ("power", None),
        ("power", True),
        ("power", 2),
        ("allinputname", ["Name"] * 7),
        ("alloutputname", ["Name"] * 16),
        ("allhdbtoutputname", None),
        ("alloutputname", [1] * 8),
    ],
)
def test_rejects_incomplete_or_unsupported_status(payload, field, value):
    payload[field] = value
    with pytest.raises(MatrixProtocolError):
        parse_status(payload)


def test_switchstatus_is_not_a_substitute(payload):
    payload["SwitchStatus"] = payload.pop("allsource")
    with pytest.raises(MatrixProtocolError, match="allsource"):
        parse_status(payload)


def test_unexpected_status_diagnostic_is_bounded_and_omits_private_values():
    with pytest.raises(MatrixProtocolError, match="comhead='video switch'"):
        parse_status({"comhead": "video switch", "private": "secret label"})
    for payload in (
        {"comhead": "secret" * 1000, "allsource": ["private label"]},
        {"comhead": {"secret": "private label"}},
        ["private label"],
    ):
        with pytest.raises(MatrixProtocolError) as error:
            parse_status(payload)
        assert len(str(error.value)) < 150
        assert "secret" not in str(error.value)
        assert "private" not in str(error.value)


def test_oversized_numeric_string_is_protocol_error(payload):
    payload["allsource"][0] = "1" * 5000
    with pytest.raises(MatrixProtocolError):
        parse_status(payload)


def test_empty_labels_fall_back_without_losing_channels(payload):
    payload["alloutputname"][0] = " "
    assert parse_status(payload).output_names[0] == "Living Room HDBT"
    payload["allhdbtoutputname"][0] = ""
    assert parse_status(payload).output_names[0] == "Output 1"


@pytest.mark.usefixtures("socket_enabled")
async def test_http_transport_serializes_and_uses_documented_wire_format(aiohttp_server, payload):
    requests = []
    active = 0
    max_active = 0

    async def handler(request):
        nonlocal active, max_active
        assert request.content_type == "application/x-www-form-urlencoded"
        body = json.loads(await request.text())
        requests.append(body)
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        if body["comhead"] == "video switch":
            return web.Response(text="unverified acknowledgement")
        return web.Response(text=json.dumps(payload), content_type="text/plain")

    app = web.Application()
    app.router.add_post("/cgi-bin/instr", handler)
    server = await aiohttp_server(app)
    async with aiohttp.ClientSession() as session:
        device = NoHassleDriver(session, server.host, server.port)
        snapshot, _ = await asyncio.gather(
            device.async_get_routes(), device.async_select_source(1, 2)
        )
    assert snapshot.routes[1] == 3
    assert requests == [
        {"comhead": "get video status"},
        {"comhead": "video switch", "source": [2, 1]},
    ]
    assert max_active == 1


@pytest.mark.usefixtures("socket_enabled")
@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (404, "", MatrixConnectionError),
        (500, "", MatrixConnectionError),
        (302, "", MatrixConnectionError),
        (200, "", MatrixProtocolError),
        (200, "<html>Login</html>", MatrixProtocolError),
        (200, "[]", MatrixProtocolError),
        pytest.param(200, "x" * 65537, MatrixProtocolError, id="oversized"),
    ],
)
async def test_http_errors(aiohttp_server, status, body, error):
    async def handler(request):
        return web.Response(status=status, text=body)

    app = web.Application()
    app.router.add_post("/cgi-bin/instr", handler)
    server = await aiohttp_server(app)
    async with aiohttp.ClientSession() as session:
        device = NoHassleDriver(session, server.host, server.port)
        with pytest.raises(error):
            await device.async_get_routes()


@pytest.mark.usefixtures("socket_enabled")
async def test_timeout_and_cancellation(aiohttp_server):
    async def handler(request):
        await asyncio.sleep(0.1)
        return web.Response(text="{}")

    app = web.Application()
    app.router.add_post("/cgi-bin/instr", handler)
    server = await aiohttp_server(app)
    async with aiohttp.ClientSession() as session:
        device = NoHassleDriver(session, server.host, server.port, timeout=0.01)
        with pytest.raises(MatrixConnectionError):
            await device.async_get_routes()
        task = asyncio.create_task(device.async_get_routes())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.parametrize(("output", "source"), [(0, 1), (9, 1), (1, 0), (1, 9), (True, 1)])
async def test_invalid_commands_do_not_send(output, source):
    device = NoHassleDriver(None, "matrix.test")
    with pytest.raises(MatrixCommandError):
        await device.async_select_source(output, source)
