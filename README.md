# SmartQasa Matrix

Home Assistant integration for video matrix devices, starting with No Hassle AV.

## Status

Repository initialized with the integration design and findings from a
NHAV-8X16V5. The integration is not implemented or installable yet. No live
Home Assistant configuration has been changed.

## Purpose

Expose reliable routing controls and confirmed source feedback through standard
Home Assistant media-player entities. Keep manufacturer protocols separate from
the Home Assistant entity layer so additional device drivers can be added
without changing the dashboard card.

The frontend matrix card lives in [smartqasa/dashboard](https://github.com/smartqasa/dashboard).
This repository contains the backend integration work only.

## Initial scope

- One media-player entity per independently routed output zone.
- Standard `source`, `source_list`, and `media_player.select_source` support.
- A shared asynchronous status poll for all outputs on a device.
- Confirmed status refresh after switching, including changes made outside HA.
- Explicit connection and command errors; unavailable devices must not appear off.
- Stable device and entity identifiers, UI setup, and unload support.
- A No Hassle driver first; Blustream and other drivers after model-specific testing.

The NHAV-8X16V5 has eight routing zones, each mirrored to HDMI and HDBaseT
connectors. Sixteen physical connections do not mean sixteen independent routes.
The common interface should not hard-code the number of zones for other models.

## Planned structure

```text
custom_components/smartqasa_matrix/
  __init__.py          Integration setup and unload
  manifest.json       Integration metadata
  const.py            Shared constants
  config_flow.py      Home Assistant UI setup
  coordinator.py      Shared polling and command coordination
  media_player.py     Standard output-zone entities
  drivers/
    base.py           Device interface and typed routing snapshots
    nohassle.py       No Hassle protocol implementation
tests/
  fixtures/           Sanitized device responses
```

These are planned files, not implemented modules. A driver should provide device
identity and capabilities, read a complete routing snapshot, and select an input
for an output. Home Assistant handles friendly names and entity lifecycle.

## First implementation milestone

1. Implement and test the No Hassle status parser using captured response shapes.
2. Add an asynchronous client with timeouts, response validation, and serialized I/O.
3. Add the shared coordinator and media-player output entities.
4. Add UI configuration and model-aware validation.
5. Test source changes, external changes, disconnects, and reconnects on hardware.
6. Document migration of existing entities before installation.

See [No Hassle protocol findings](docs/nohassle-protocol.md) for the current
evidence and unresolved validation work.
