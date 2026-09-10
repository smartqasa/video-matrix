# Architecture and adding a manufacturer

```text
Dashboard / HA UI / automations
             |
media_player.select_source + source/source_list
             |
  media_player.MatrixOutput
             |
  coordinator.MatrixCoordinator
             |
    drivers.base.MatrixDriver
             |
    NoHassleDriver today
    Blustream / other drivers later
```

## Boundaries

`drivers/base.py` has no Home Assistant imports. It defines:

- `MatrixIdentity`: manufacturer, model, input count, independent output count.
- `RoutingSnapshot`: immutable routes, input names, output names, and device power.
  Numeric IDs are one-based; tuple index is ID minus one. Mirrored connectors
  share a zone. Counts need not be eight or square.
- `MatrixDriver`: `identity`, `async_get_routes`, `async_select_source`, and
  `async_close`. Reads return complete validated snapshots or raise `MatrixError`.
  Writes request one route; read-back establishes success.

Drivers handle HTTP/TCP/serial framing, authentication, bounded I/O, validation,
and vendor ID conversion. A driver may aggregate several vendor reads into one
snapshot. It must not publish partial state or merge channels with duplicate names.

`drivers/registry.py` registers manufacturers, supported models, default ports,
and factories. Factories receive an HA-owned HTTP session, host, port, and model;
a TCP driver can ignore the HTTP session and own its socket. Add connection
settings when an actual driver requires them. Drivers close only resources they
own. Probe drivers close after validation, running drivers on unload/setup failure.

`coordinator.py` owns a device-wide transaction lock. Polls cannot interleave
between a write and its confirmation reads, and two output commands cannot race.
Each validated read publishes actual state for all zones. Three mismatching reads
raise an action error while preserving the last actual state. Read failure marks
all entities unavailable. Failed writes trigger a read to reconcile possible
hardware changes, but still raise the write error and are never blindly repeated.

`media_player.py` knows only numeric outputs, snapshots, and HA features. It does
not inspect vendor HTTP fields, assume eight outputs, or predict source changes.
HA manages names, entity IDs, and areas. Source labels resolve at the entity
boundary, with optional HA names keyed by numeric input ID. Duplicate/blank labels
get deterministic unique names; exact exposed names map back to their numeric IDs.

## Adding a driver

1. Collect sanitized reads, write responses, model/firmware, channel counts,
   numbering, power behavior, and confirmation timing. Identify mirrored connectors.
2. Implement the shared interface in a driver module with asynchronous bounded I/O
   and explicit errors. Close owned connections, including on cancellation.
3. Register models and factories. Add connection fields/translations as needed,
   without adding protocol logic to entities or the dashboard.
4. Add parser/transport fixtures and HA tests for counts, mapping, failures, and
   confirmed switching.
5. Physically test switching, external changes, power cycles, reconnects, and
   concurrent vendor UI use before advertising support.

A synthetic two-input, three-output driver exercises the same HA entities and
source service. It proves the boundary, not additional hardware support. Breakaway
audio, disconnected routes, or unknown power reporting need explicit capability
and snapshot extensions backed by protocol evidence.
