# Video Matrix

A local Home Assistant integration for video matrix routing. No Hassle AV is the
first supported manufacturer. Device protocols sit behind a shared interface so
future Blustream and other drivers use the same entities and dashboard card.

## Status

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

1. Until a HACS-installable release is available, download/check out the **beta** branch and
   copy `custom_components/video_matrix` into HA's `/config/custom_components/`.
   See the HACS publishing requirements below.
2. Restart HA and open **Settings → Devices & services → Add integration → Video Matrix**.
3. Select **No Hassle AV**, enter the host/IP and HTTP port (normally 80), and
   choose **NHAV-8X16V5**. Setup validates a read without changing routes.
4. Optionally use **Configure** to override input names. Blank fields use device
   labels. Rename output entities and assign their areas through HA.

### HACS installation

HACS is the intended route for installation and updates once the repository is
prepared for distribution. Manual copying is a temporary workaround, not a
requirement of this integration or of beta testing.

The repository is now **public**, satisfying HACS's visibility requirement.
The remaining blocker is the distribution layout: the default `main` branch
contains design notes only, and no GitHub release packages the implementation yet.
HACS uses published releases or the default branch; the separate development
branch is not automatically offered. See
[HACS integration publishing](https://hacs.xyz/docs/publish/integration/).

Enabling HACS installation still requires an installable default branch/release
layout. Beta builds can then be distributed as clearly marked prereleases while
keeping `main` and `beta` separate. The included `hacs.json` and integration layout
provide the packaging foundation.

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

`main` is the stable branch. `beta` contains ongoing development and hardware
validation work. The initial implementation goes to `beta`; promote a reviewed,
validated beta revision to `main` when ready. Download the appropriate branch and
avoid treating beta as a hardware-validated release.

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m ruff check custom_components tests
.venv/bin/python -m ruff format --check custom_components tests
.venv/bin/python -m pytest --cov=custom_components.video_matrix --cov-report=term-missing
```

The pinned test helper installs HA 2026.9.1. See [architecture and adding drivers](docs/architecture.md),
[testing](docs/testing.md), and [reference integration review](docs/reference-integrations.md).
