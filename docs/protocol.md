# RS-232 protocol notes

Facts about the Monoprice 6-zone amplifier's RS-232 protocol that the code
relies on but does not restate inline. "Verified" means observed against
real hardware or documented in the RS-232 spec and pymonoprice's
`ZoneStatus`; "unverified" means inferred from behavior and not confirmed
against the vendor spec.

Where a fact is marked verified on hardware, it was observed on a single
unit (one 10761 controller, no expansion units, FTDI adapter at 9600 8N1).

## Reply framing

Every reply ends with an EOL sequence of `` \r\n# ``. How many of those a
command produces depends on the command, and reading the wrong number is
what leaves a frame in the buffer to be mis-read as the answer to whatever
is sent next.

| Command shape | Example | EOL frames | Status |
| --- | --- | --- | --- |
| Control write | `<11VO12` | 1 | Verified |
| Zone status query | `?11` | 2 | Verified |
| Single-field query | `?11VO` | 2 | Verified |
| Rename/welcome acknowledgement | `1<AppleTV ` answers `Done.` | 2 | Verified |
| Rejection | any malformed command answers `Command Error.` | 2 | Verified |
| Whole-unit query | `?10` | 7: one leading marker frame plus one record per zone | Verified |

`pymonoprice`'s `_process_request` takes the count as `num_eols_to_read` and
defaults to 1, so anything but a control write has to pass it explicitly.
`api.py` uses `REPLY_EOLS` for the two-frame replies; `send_raw` cannot know
the count ahead of the send, so it reads one frame and then drains.

## The unit address is not a master zone

`?N0` (`?10`, `?20`, `?30`) is not a unit summary. The amplifier answers it
with one full status record per zone. Counted in EOL sequences that is seven,
because the reply opens with the same bare marker frame every reply does, and
`pymonoprice.all_zone_status` reads exactly that count. Counted in records it
is six, one per zone, which is what jnewland/mpr-6zhmaut-api's
`queryControllers()` waits for. Reading it through `zone_status`
parses the first frame, so the reply looks like a valid status for zone
`N1`, and leaves the remaining five frames unread.

Writes are different: `<N0..` is accepted and broadcasts to every zone in
the unit, so a master entity is meaningful for control. It has no readable
state of its own, and `coordinator.py` mirrors the unit's first zone into
it.

| Fact | Status |
| --- | --- |
| `?10` returns six status *records* (seven EOL frames, the first being the leading marker), `?20`/`?30` return nothing when the unit is absent | Verified |
| `<10VO10` is accepted and broadcasts; on the 10761 and other 6-zone units `<17..`, `<27..`, `<99..` answer `Command Error.` | Verified on a 10761 |

Zone ids above 6 per unit are rejected *on this model*, not by the protocol.
The same command set runs 4-zone and 8-zone units (Monoprice 44519 and 44518,
Dayton DAX88) where `11..14` or `11..18` are valid, so this row is a fact
about the 10761 and must not be read as a protocol invariant that would block
supporting them.

## Writes only apply while the zone is powered on

The amplifier accepts volume, mute, source, treble, bass and balance writes
with a normal echo whether or not the zone is on, but only applies them
while it is on. Sent to a powered-off zone they are silently discarded.

| Attribute | Zone on | Zone off | Status |
| --- | --- | --- | --- |
| `VO`, `MU`, `CH`, `TR`, `BS`, `BL` | Applied | Silently ignored | Verified |
| `PR` (power), `DT` (do not disturb) | Applied | Applied | Verified |

There is no error to detect, so a caller that needs one of these to stick
has to power the zone on first. Every setter in `media_player.py` and
`number.py` re-reads the zone afterwards, so Home Assistant shows the value
the amplifier actually kept rather than the one that was requested.

## PA is status only on this hardware

`<ZZPA01` is accepted with a normal echo and the `PA` field never changes,
even with the zone powered on. The command is not malformed: `<ZZPA1` does
answer `Command Error.`, so the amplifier is parsing `<ZZPA01` and choosing
to ignore it. The field reports the hardware paging input.

This is not a quirk of one unit. The openHAB `monopriceaudio` binding states
it as a product fact across the 10761, DAX66, 44519 and 44518: activating
"Page All Zones" can only be done through the **+12V trigger input on the back
of the amplifier**. That binding models paging as a read-only contact and
offers no page write at all, and pyxantech defines no PA command in any of its
protocol files. jnewland/mpr-6zhmaut-api exposes `pa` for POST but never shows
it working.

So the way to page is to wire the announcement trigger to the amplifier's +12V
input; there is no RS-232 route. `switch.py` still sends `<ZZPA01` and reads
the flag back, raising when it did not take, because a silent no-op is worse
than an error. It is kept as a switch rather than removed so existing
dashboards keep working, but no known implementation believes the write does
anything.

## Out-of-range values are accepted without complaint

`<11VO39`, `<11BL21`, `<11TR15`, `<11CH07` and `<11CH00` are all echoed
normally with no `Command Error.`, so the amplifier does not range-check
them. `pymonoprice`'s formatters clamp to the documented ranges before the
bytes ever reach the wire, which is the only guard; `send_raw` bypasses it
by design.

## EQ and balance wire ranges

| Control | Wire range | Display mapping | Status |
| --- | --- | --- | --- |
| Volume (VO) | 0-38 | Shown as a 0-1 fraction of `MAX_VOLUME` | Verified |
| Bass (BS) | 0-14 | Signed dB: 0 = -7dB, 14 = +7dB | Verified (RS-232 spec, pymonoprice `ZoneStatus`) |
| Treble (TR) | 0-14 | Signed dB: 0 = -7dB, 14 = +7dB | Verified (RS-232 spec, pymonoprice `ZoneStatus`) |
| Balance (BL) | 0-20 | 0 = full left, 10 = center, 20 = full right | Verified (RS-232 spec) |
| Source (CH) | 1-6 | Source names from the config entry | Verified |

Both ends of every range were accepted and read back unchanged on hardware.
`number.py` displays the translated signed value to the user and translates
back to the 0-14/0-20 wire value before sending. `const.py`'s
`ATTR_BALANCE`/`ATTR_BASS`/`ATTR_TREBLE` service fields carry the raw wire
value, not the display value.

## Command timing

The amplifier answers one command at a time and has no flow control, so the
only thing keeping a command from arriving before the previous reply is fully
read is the caller's own pacing.

| Interval | Constant | Value | Why |
| --- | --- | --- | --- |
| Between any two commands | `gateway.py::MIN_COMMAND_INTERVAL` | 0.05s | pyxantech sets this on every series it supports and enforces it with an explicit sleep; its README records the value moving from 400ms down to 50ms |
| Before each expansion-unit probe | `serial.py::EXPANSION_PROBE_SPACING` | 1.0s | A probe that times out is read as "unit absent", so a slow unit would lose its entities until the next rediscovery. jnewland/mpr-6zhmaut-api spaces the equivalent startup queries by a full second |
| After a baud rate change, before clearing | `api.py::BAUD_SETTLE` | 0.25s | Measured; see the baud section above |
| After the first frame of an unpredictable reply | `api.py::DRAIN_SETTLE` | 0.15s | `send_raw` cannot know the frame count before it sends |

The gateway's lock serializes access but does not space commands apart, so the
floor is held inside it, measured from when the previous command finished. A
command that raised still spaces the next one: the floor protects the
amplifier, and a failure is exactly when the line is least likely to be quiet.

Measured cost on a single 10761 at 9600: a six-zone poll goes from 0.22s to
0.47s against a 5s poll interval, and endpoint validation from 0.88s to 1.88s
because of the one expansion probe.

The expansion-probe spacing is a precaution on published precedent, not a fix
validated against a reproduction. The bench that produced this document had
one unit and no expansion units, so whether the previous back-to-back probe
ever actually missed a slaved unit is still unverified.

## Status response framing

| Fact | Status |
| --- | --- |
| A zone status response is framed as `` \r\n#>11...\r\n# `` | Verified |
| Reading it takes two reads: the first consumes the leading `` \r\n# `` marker, the second consumes the actual status record | Verified |

See `serial.py::_read_zone_status`.

One reference disagrees about field order and is wrong. pyxantech's
`protocols/monoprice.yaml` parses the record as zone, power, source, mute,
do-not-disturb, volume, treble, bass, balance, unknown, keypad, with its `dnd`
group only one character wide, which misaligns everything after it. Its own
`protocols/dax66.yaml`, the openHAB binding, jnewland/mpr-6zhmaut-api, the
DAX88 manual and `pymonoprice.ZoneStatus` all agree on zone, PA, power, mute,
DND, volume, treble, bass, balance, source, keypad, which is what this
integration observes on the wire. Do not "correct" `pymonoprice` to match
pyxantech's Monoprice file.

## Baud rate change behavior

| Fact | Status |
| --- | --- |
| The amplifier switches to the new baud rate immediately after receiving the set-baud command and does not reply at the old rate | Verified |
| Waiting for a reply at the old rate after sending the command always times out | Verified |
| The switch is unconditional: it happens on receipt, whether or not the caller ever confirms it | Verified |
| The tail of the echo is still in flight at the old rate when the switch lands, and decodes as garbage at the new one | Verified |
| A settle of at least 0.05s between switching the local port and clearing its buffers is required; below that the confirmation reads the stale echo | Verified (measured on a 10761) |
| `<{baud}` is the command shape | Verified, and corroborated by jnewland/mpr-6zhmaut-api |
| The six supported rates are 9600, 19200, 38400, 57600, 115200, 230400 | Verified at 9600/19200/38400/115200, corroborated for all six by jnewland/mpr-6zhmaut-api |
| Connecting at the wrong rate does not lock the controller | Reported by jnewland/mpr-6zhmaut-api, not independently verified |
| Power loss returns the controller to 9600; removing power for 30 seconds forces it | Reported by jnewland/mpr-6zhmaut-api, not independently verified |

See `api.py::MonopriceExtended.set_baud_rate`, which sends the command,
switches the local port's rate, waits `BAUD_SETTLE` for the old-rate echo to
finish arriving, and only then clears the buffers and queries zone 11.
Clearing first is what fails: `reset_input_buffer` discards what has already
arrived, so bytes still in flight land afterwards and are read as the reply.
The same race is why a leftover frame elsewhere in the protocol is not always
masked by the reset at the start of the next request.

A False return from `set_baud_rate` therefore does not mean the amplifier
stayed where it was. Recovery is `gateway.py::_ensure_link_sync`, which probes
the supported rates and pins whichever answers; because a wrong-rate
connection cannot lock the controller, that sweep is safe by design rather
than by luck.

`probe_baud_rate` only moves the local port and confirms zone 11, so it never
changes what the amplifier is set to.

Over a `socket://` bridge none of this applies to the far side: changing
`self._port.baudrate` moves only the local end, and the bridge's own fixed
rate governs the wire to the amplifier.

## Keypad commands

| Command | Effect | Status |
| --- | --- | --- |
| `M` | Sets the keypad's boot welcome message | Verified |
| A source number (1-6) | Renames that source's label on the keypad | Verified |

Both answer `Done.`. An index outside 1-6 answers `Command Error.`, so
`api.py` rejects it before sending. The payload is a fixed 8 characters and
must be 7-bit ASCII; anything else raises before it reaches the port.

Neither string can be read back. There is no query that returns the current
source labels or welcome message, so the only record of them is whatever the
user set. `text.py`'s entities are therefore write-only, and their state is
the last value this integration sent, not what the keypad shows.

## No endpoint validation on a port that is not a UART

A character device that exists but cannot be configured as a serial port
fails inside `termios`, whose `error` derives from `Exception` rather than
`OSError`. `serial.py` includes it in `_PORT_ERRORS` so the config flow
reports "cannot connect" instead of raising, and so the port is closed.
