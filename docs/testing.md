# Testing and hardware acceptance

## Automated tests

Tests run in Home Assistant's custom-integration harness, with local fake HTTP
servers where transport matters. They do not contact household devices.

`fixtures/video_status.json` is a **reconstructed minimal response** using the
documented field shape and route values with illustrative labels. It is not a
verbatim complete capture. Malformed/off/delayed responses are synthetic. Off-state
schema and confirmation timing still need hardware verification.

Tests cover the trailing zero, missing `allsource`, wrong command identity,
counts/ranges/types, duplicate labels, HTTP/JSON errors, redirects, size limits,
timeouts, serialization, cancellation, UI setup/options/reconfiguration, stable
IDs, one poll for all zones, switching, external changes, recovery, and unload.

## Hardware acceptance (pending)

Use two visually distinguishable connected sources and a known output. Record
firmware, timestamps, numbered channels, redacted status, and the observed picture.
Do not mark a test passed based only on HTTP or a UI selection.

1. Compare all eight routes and labels against the vendor UI. Confirm no ninth
   zone exists and both connectors in each mirrored pair share the route.
2. Call `media_player.select_source` for another input. Verify the physical
   picture, entity `source`, and dashboard selection agree. Record the switch
   response without credentials or household details.
3. Switch back and repeat on another zone. Confirm unrelated routes stay unchanged.
4. Change a route in the vendor UI/front panel. Confirm HA and the card follow
   within the next ten-second poll plus request time.
5. Disconnect networking. Confirm outputs become unavailable after the next read
   times out, not off. Reconnect and verify automatic recovery.
6. Power off/on through the matrix controls. Record the exact off-state response.
   Complete supported `power: 0` reports off; unreachable/incomplete status reports
   unavailable until a valid response returns.
7. Issue two HA output commands and use the vendor UI during a selection. Verify
   actual final routes and visible errors if an external controller overrides a
   route before confirmation. External controllers cannot share HA's lock.
8. Restart HA, rename sources, reconfigure the same device's address, and unload.
   Confirm entity IDs persist and polling stops on unload.

Only after these tests should that model/firmware be marked physically validated.
