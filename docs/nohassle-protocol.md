# No Hassle protocol findings

## Inspected hardware

- Model: `NHAV-8X16V5`
- Main firmware: `V1.13.24`
- Eight inputs and eight independent routing zones.
- Each zone has mirrored HDMI and HDBaseT outputs.

The device's switching page presents eight rows, each pairing its HDMI and
HDBaseT output names. The [manufacturer describes the mirrored output arrangement](https://nohassleav.com/products/8x16-8x8-hdr-18gbps-hdbaset-4k-matrix-switcher-arc-downscaling-16x16-with-8-receivers-hdmi-2-0a-2-0-cat6-cat5e-hdmi-hdcp2-2-routing-spdif-audio-control4-savant-home-automation).

## Verified status reads

The following read-only requests succeeded against the hardware:

```http
POST /cgi-bin/instr
Content-Type: application/x-www-form-urlencoded

{"comhead":"get video status"}
```

Despite the content type, the device's web UI sends a JSON body. The same
endpoint also accepts `get status` and `get output status` read commands.

Relevant video-status fields:

- `comhead`: should equal `get video status`.
- `power`: observed as `1` when powered on.
- `allsource`: one-based input numbers for output zones.
- `allinputname`: input labels.
- `alloutputname`: HDMI output labels.
- `allhdbtoutputname`: HDBaseT output labels.

An observed `allsource` value was `[1,3,1,4,5,6,7,8,0]`. The first eight values
represent the eight zones. A ninth trailing zero appeared in video status;
output status returned only eight entries. The driver must not invent a ninth
zone from this response. Derive and validate the zone count against model
capabilities and output-name arrays.

Input labels configured in Home Assistant may differ from the device's labels.
Preserve a stable numeric input ID internally and map friendly names at the
entity boundary.

## Switching command found in the vendor UI

```json
{"comhead":"video switch","source":[2,1]}
```

The array is `[input, output_zone]`, using one-based numbers. This requests
input 2 on zone 1. Direct JSON switching and route readback were verified on
September 10, 2026. A test route was changed and restored, with the complete route
array checked after restoration. Physical picture verification remains pending.

During a real route change, subsequent `get video status` requests can return a
39-byte JSON acknowledgement with `comhead: "video switch"` and no `allsource`.
One test needed a second status read; restoring the route needed a third read.
The stale acknowledgements took about three seconds each. A same-route write
did not reproduce this behavior. An acknowledgement must never count as routing
feedback: retry status reads within the confirmation budget, without resending
the switching command or accepting the wrong response shape.

The user confirmed that their existing Home Assistant integration can switch
inputs. They subsequently reported that selected-source feedback is missing.
Working commands therefore do not establish working status updates.

## Existing integration's likely feedback failure

The [upstream integration](https://github.com/IDmedia/hass-nohassle_hdmi_matrix/blob/master/custom_components/nohassle_hdmi_matrix/media_player.py)
has a mode-2 parser that reads `response['SwitchStatus']`. The inspected device
returns `allsource` instead. A missing `SwitchStatus` raises an exception;
upstream catches it broadly, sets the entity state to `off`, and does not
populate the selected source.

Direct checks found:

- `/AutoGetAllData` returned HTTP 404.
- `/cgi-bin/submit?cmd=getpage2!` returned HTTP 200 with an empty body.
- The subsequent `/cgi-bin/query` returned an `allsource` response without
  `SwitchStatus`.

This reproduces a response shape that the upstream parser cannot handle.
The installed integration revision has not been inspected; confirm it before
preparing any migration or patch to that installation.

Do not select a protocol based only on an HTTP 200 response. Validate command
identity, required fields, array lengths, and channel ranges. Report errors
rather than silently preserving or fabricating state.

## Integration design

Use one shared poll for the complete matrix, with each media-player entity
reading its zone from the latest snapshot. Refresh actual state after commands
and keep external changes visible. Device communication failures should mark
entities unavailable rather than imply the matrix is powered off.

Source selection and source feedback follow Home Assistant's standard
[media-player contract](https://developers.home-assistant.io/docs/core/entity/media-player/).
Shared polling follows its
[DataUpdateCoordinator guidance](https://developers.home-assistant.io/docs/integration_fetching_data/).

## Still to verify

- Write acknowledgement success/error fields beyond the observed command identity.
- Physical picture changes and mirrored connector behavior.
- Powered-off, disconnected, malformed, and partially populated responses.
- Command/status sequencing while the web UI is also active.
- Other No Hassle models and firmware versions.
- The exact Blustream model and protocol before adding that driver.

Device addresses, credentials, and household configuration are deliberately
excluded from repository examples.

## Implemented behavior

The `video_matrix` integration now uses `get video status` and parses `allsource`.
Its NHAV-8X16V5 profile validates eight input names, eight HDMI names, eight HDBaseT
names, and eight one-based routes. Only the optional ninth zero is discarded.
Missing, partial, or out-of-range data fails the snapshot rather than preserving
stale selected-source feedback.

JSON switching is implemented with serialized read-back confirmation. An
acknowledgement is not proof of success. HTTP errors are surfaced; HTTP 200 is
followed by up to three reads that must show the requested route. Protocol or
connection failures during confirmation consume a read attempt, without briefly
marking every output unavailable if a later attempt succeeds. Exhausted failed
reads still make the outputs unavailable. If the write itself failed, its error
is preserved even if subsequent status reconciliation also fails. Diagnostics
include bounded JSON shape and allowlisted command identity, not arbitrary payloads.
Automated tests use simulated devices; physical picture tests remain pending. See
[testing](testing.md) and [reference review](reference-integrations.md).
