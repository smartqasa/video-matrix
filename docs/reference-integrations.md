# Reference integration review

These implementations were reviewed as protocol/design references; their code was
not copied. They do not prove physical behavior on the user's installed firmware.

## IDmedia original

[Source](https://github.com/IDmedia/hass-nohassle_hdmi_matrix/blob/master/custom_components/nohassle_hdmi_matrix/media_player.py)
combines transport and entities. It probes `/AutoGetAllData` and
`/cgi-bin/submit?cmd=getpage2!` by HTTP status. The second mode reads `SwitchStatus`
from `/cgi-bin/query`, which misses the NHAV-8X16V5 `allsource` response.
Read exceptions set off; switch exceptions are swallowed. Its numeric source-ID
to friendly-name mapping is useful to preserve when migrating.

## funtast Lightware fork

[Source at b4b4183](https://github.com/funtast/hass-lightware_hdmi_matrix/blob/b4b4183a6192a6bc0f2fcbf40bb23d3308c91f07/custom_components/nohassle_hdmi_matrix/media_player.py)
still lives under `nohassle_hdmi_matrix` and uses the same two HTTP endpoint
families and `SwitchStatus` parsing. Its title names Lightware, but the reviewed
source does not establish a distinct Lightware protocol. It cannot establish
Lightware support or a Blustream implementation.

## UnintelligibleMaker fork

[Controller at d070b03](https://github.com/UnintelligibleMaker/hass-nohassle_hdmi_matrix/blob/d070b0316d4a8079f716dcda3f5c3220e48fc441/custom_components/nohassle_hdmi_matrix/nohassle_hdmi_matrix.py)
separates a controller from select/switch entities and uses JSON POST requests to
`/cgi-bin/instr`. It corroborates `video switch` with `[source_num, device_num]`
and compares response `comhead` with the command. Its video-status method sends
`get videostatus`, whereas our hardware notes verified `get video status`.

This supports using a separate driver interface. Its synchronous requests, sleeps,
and retries are not used here. Video Matrix keeps the verified spelling and IDs,
serializes asynchronous transactions, and confirms routes using `allsource`.
Acknowledgements alone do not establish routing success.
