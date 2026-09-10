# Testing and hardware acceptance

## Automated tests

Tests run in Home Assistant's custom-integration harness, with local fake HTTP
servers where transport matters. They do not contact household devices.

`fixtures/video_status.json` is a **reconstructed minimal response** using the
documented field shape and route values with illustrative labels. It is not a
verbatim complete capture. Malformed/off responses are synthetic. Off-state
schema still needs hardware verification. Stale acknowledgement sequencing is
based on the live observations below.

Tests cover the trailing zero, missing `allsource`, wrong command identity,
counts/ranges/types, duplicate labels, HTTP/JSON errors, redirects, size limits,
timeouts, serialization, cancellation, UI setup/options/reconfiguration, stable
IDs, one poll for all zones, switching, external changes, recovery, and unload.

## Live checks on September 10, 2026

On an NHAV-8X16V5 running firmware V1.13.24:

- A direct JSON route change returned a `video switch` acknowledgement. The
  first status read also returned that acknowledgement, and the second returned
  valid routing data. Restoring the route needed three status reads. The complete
  route array was checked after restoration.
- After installing 0.1.0b2 and restarting HA, standard `media_player.select_source`
  calls changed a test output to another source and restored it. HA feedback and
  the SmartQasa matrix card showed the requested source after each call. A matrix
  log search found no errors after these calls.
- Device labels and HA `source_list` matched; existing card display-name overrides
  continued to work with the device's exact source values.

These checks establish route readback and HA/card feedback. They do not establish
physical picture changes, power-state handling, or every acceptance item below.

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
