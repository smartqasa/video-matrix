"""No Hassle NHAV-8X16V5 JSON-over-HTTP protocol."""

import asyncio
import json
from typing import Any

import aiohttp
from yarl import URL

from .base import (
    MatrixCommandError,
    MatrixConnectionError,
    MatrixIdentity,
    MatrixProtocolError,
    RoutingSnapshot,
)

NHAV_8X16V5 = MatrixIdentity("No Hassle AV", "NHAV-8X16V5", 8, 8)
MODELS = {NHAV_8X16V5.model: NHAV_8X16V5}
MAX_RESPONSE_BYTES = 64 * 1024


def _integer(value: Any, field: str) -> int:
    """Accept integers and decimal strings, but never floats or booleans."""
    if type(value) is int:
        return value
    if isinstance(value, str) and len(value) <= 10 and value.isascii() and value.isdecimal():
        return int(value)
    raise MatrixProtocolError(f"Invalid {field}: expected an integer")


def _names(payload: dict, field: str, count: int) -> tuple[str, ...]:
    values = payload.get(field)
    if not isinstance(values, list) or len(values) != count:
        raise MatrixProtocolError(f"Invalid {field}: expected {count} names")
    if not all(isinstance(value, str) for value in values):
        raise MatrixProtocolError(f"Invalid {field}: expected text names")
    return tuple(value.strip() for value in values)


def parse_status(payload: Any, identity: MatrixIdentity = NHAV_8X16V5) -> RoutingSnapshot:
    """Validate the documented video response, including its optional sentinel."""
    if not isinstance(payload, dict) or payload.get("comhead") != "get video status":
        raise MatrixProtocolError("Expected a get video status response")
    inputs = _names(payload, "allinputname", identity.input_count)
    outputs = _names(payload, "alloutputname", identity.output_count)
    hdbt = _names(payload, "allhdbtoutputname", identity.output_count)
    raw_routes = payload.get("allsource")
    if not isinstance(raw_routes, list):
        raise MatrixProtocolError("Missing allsource routing array")
    routes = tuple(_integer(value, "allsource") for value in raw_routes)
    # This firmware reports eight zones plus an optional, non-routing zero.
    if len(routes) == identity.output_count + 1 and routes[-1] == 0:
        routes = routes[:-1]
    if len(routes) != identity.output_count:
        raise MatrixProtocolError("Routing count does not match the configured model")
    if any(source < 1 or source > identity.input_count for source in routes):
        raise MatrixProtocolError("Routing input is outside the model's input range")
    power = _integer(payload.get("power"), "power")
    if power not in (0, 1):
        raise MatrixProtocolError("Invalid power state")
    return RoutingSnapshot(
        routes=routes,
        input_names=inputs,
        output_names=tuple(
            hdmi or paired or f"Output {index}"
            for index, (hdmi, paired) in enumerate(zip(outputs, hdbt, strict=True), 1)
        ),
        powered_on=bool(power),
    )


class NoHassleDriver:
    """Use the HA-owned session, bounded requests, and one device I/O lock."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int = 80,
        model: str = NHAV_8X16V5.model,
        *,
        timeout: float = 5,
    ) -> None:
        self.identity = MODELS[model]
        self._session = session
        self._url = URL.build(scheme="http", host=host, port=port, path="/cgi-bin/instr")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._lock = asyncio.Lock()

    async def _request(self, payload: dict) -> bytes:
        try:
            async with self._session.post(
                self._url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self._timeout,
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    raise MatrixConnectionError(f"Matrix returned HTTP {response.status}")
                data = bytearray()
                async for chunk in response.content.iter_chunked(4096):
                    data.extend(chunk)
                    if len(data) > MAX_RESPONSE_BYTES:
                        raise MatrixProtocolError("Matrix response exceeds the size limit")
                return bytes(data)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise MatrixConnectionError("Could not communicate with the matrix") from err

    async def async_get_routes(self) -> RoutingSnapshot:
        async with self._lock:
            body = await self._request({"comhead": "get video status"})
            try:
                payload = json.loads(body)
            except (ValueError, UnicodeDecodeError) as err:
                raise MatrixProtocolError("Matrix did not return JSON status") from err
            return parse_status(payload, self.identity)

    async def async_select_source(self, output: int, source: int) -> None:
        if type(output) is not int or not 1 <= output <= self.identity.output_count:
            raise MatrixCommandError("Output is outside the model's zone range")
        if type(source) is not int or not 1 <= source <= self.identity.input_count:
            raise MatrixCommandError("Source is outside the model's input range")
        async with self._lock:
            # The acknowledgement format is unverified. HTTP 200 is NOT success:
            # the coordinator must read and confirm the actual route afterwards.
            await self._request({"comhead": "video switch", "source": [source, output]})

    async def async_close(self) -> None:
        """No owned connection: aiohttp session lifetime belongs to Home Assistant."""
