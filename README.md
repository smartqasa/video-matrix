# Video Matrix

A local Home Assistant integration for video matrix routing. No Hassle AV is the
first supported manufacturer. Device protocols sit behind a shared interface so
future Blustream and other drivers use the same entities and dashboard card.

## Status

The first preview, **0.1.0b1**, is available for installation through HACS.
Implemented and tested with Home Assistant 2026.9.1 and Python 3.14; the first
release targets HA 2026.9 or newer. Automated tests use simulated devices.
Direct JSON switching and physical picture changes on the NHAV-8X16V5 still need
a hardware acceptance test. No running Home Assistant instance has been modified.

| Manufacturer | Model | Inputs | Independent outputs | Feedback |
| --- | --- | --- | --- | --- |
| No Hassle AV | NHAV-8X16V5 | 8 | 8 mirrored HDMI/HDBaseT pairs | `allsource` |

Sixteen connectors do not mean sixteen independent routes. Other models and
manufacturers are not advertised until their drivers are implemented and tested.
See [protocol evidence](docs/nohassle-protocol.md).

## Behavior

- One standard `media_player` entity per independently routed output, exposing
  `source`, `source_list`, and `media_player.select_source`.
- One shared read every ten seconds, including changes made outside HA.
- Serialized switching and read-back confirmation. Up to three reads, half a
  second apart, allow routes to settle. Writes are never automatically repeated.
- Failed reads mark outputs unavailable. A valid power state of zero means off.
  There are no unverified power, volume, or playback controls.
- Optional friendly source names mapped to stable input numbers. Duplicate names
  are disambiguated, without merging channels.
- UI setup, options, connection reconfiguration, and unload support.

## Installation

1. Open **HACS → ⋮ → Custom repositories**.
2. Add `https://github.com/smartqasa/video-matrix` with type **Integration**.
3. Open **Video Matrix** in HACS and choose **Download**. Select `0.1.0b1` if beta
   versions are shown. Otherwise, select `main`, which contains the same initial
   preview. HACS downloads the files into the correct directory.
4. Restart HA if HACS requests it, then open
   **Settings → Devices & services → Add integration → Video Matrix**.
5. Select **No Hassle AV**, enter the host/IP and HTTP port (normally 80), and
   choose **NHAV-8X16V5**. Setup validates a read without changing routes.
6. Optionally use **Configure** to override input names. Blank fields use device
   labels. Rename output entities and assign their areas through HA.

The repository is public and its default `main` branch contains the complete
`custom_components/video_matrix` directory and `hacs.json`. This lets HACS validate
the repository even when prereleases are hidden. If you previously received
“Repository structure for main is not compliant,” close the custom-repository
dialog, reopen it, and add the repository again.

For installation without HACS, copy `custom_components/video_matrix` from the
desired release into HA's `/config/custom_components/` and restart HA.

This profile uses the documented unauthenticated HTTP endpoint. HTTPS,
authentication, older `SwitchStatus` firmware, and alternate endpoints are not
automatically guessed. Unsupported or incomplete status fails visibly.

Use **Reconfigure** to change the address of the same matrix. Entity/device IDs
derive from the persisted config entry and output number, not an IP or label.
They survive restarts, label changes, and address reconfiguration. No hardware
serial number was established, so duplicate prevention compares normalized host
and port; different aliases for the same device cannot be detected. Removing and
re-adding the integration creates new IDs.

## SmartQasa dashboard

The existing `custom:matrix-card` uses the standard media-player contract. No
manufacturer-specific card changes or custom routing action are needed. Use each
**matrix output** entity, not its TV entity. Each source `value` must exactly
match an advertised `source_list` entry; display `name` may differ.

```yaml
type: custom:matrix-card
name: Video Matrix
sources:
  - value: Roku 1
    name: Streaming
  - value: Media Server
    name: Movies
outputs:
  - value: 1
    name: Living Room TV
    entity: media_player.matrix_living_room
```

Names above are examples. Inspect your created entities before using them.
Standard HA actions work too:

```yaml
action: media_player.select_source
target:
  entity_id: media_player.matrix_living_room
data:
  source: Roku 1
```

## Migrating from the existing integration

1. Back up HA. Record output entity IDs, numbered input/source names, room
   assignments, dashboard references, and automation actions.
2. Install Video Matrix and compare read-only feedback. Disable the old integration
   during testing if it polls aggressively.
3. Copy existing friendly source names into options by **input number**; the
   device labels may differ from the existing HA labels.
4. Complete the [hardware acceptance procedure](docs/testing.md).
5. Disable/remove the old integration or YAML platform. Update card and automation
   references, or free the old entity IDs and assign them to the new outputs
   through HA's entity settings. Registry IDs differ; migration is not automatic.
6. Replace `media_player.hdmi_matrix_set_zone` actions with standard
   `media_player.select_source`, preserving exact source-name matching.

The installed old revision has not been inspected. Upstream code does not prove
the behavior of that installation.

## Development

`main` holds the installable release baseline that HACS validates. `beta` contains
ongoing development and hardware validation work. The initial baseline is explicitly
a **beta preview**, not a hardware-validated stable release. Publish previews as
GitHub prereleases (`0.1.0b1`, `0.1.0b2`, ...) and promote reviewed beta revisions to
`main`; stable releases follow successful hardware validation. Both branches retain
the complete integration layout. Keep each release tag and manifest version aligned.

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m ruff check custom_components tests
.venv/bin/python -m ruff format --check custom_components tests
.venv/bin/python -m pytest --cov=custom_components.video_matrix --cov-report=term-missing
```

The pinned test helper installs HA 2026.9.1. See [architecture and adding drivers](docs/architecture.md),
[testing](docs/testing.md), and [reference integration review](docs/reference-integrations.md).
