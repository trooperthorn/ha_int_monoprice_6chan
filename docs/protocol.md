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
| Whole-unit query | `?10` | 7 (one per zone) | Verified |

`pymonoprice`'s `_process_request` takes the count as `num_eols_to_read` and
defaults to 1, so anything but a control write has to pass it explicitly.
`api.py` uses `REPLY_EOLS` for the two-frame replies; `send_raw` cannot know
the count ahead of the send, so it reads one frame and then drains.

## The unit address is not a master zone

`?N0` (`?10`, `?20`, `?30`) is not a unit summary. The amplifier answers it
with one full status frame per zone, seven EOL frames in total, which is
what `pymonoprice.all_zone_status` reads. Reading it through `zone_status`
parses the first frame, so the reply looks like a valid status for zone
`N1`, and leaves the remaining five frames unread.

Writes are different: `<N0..` is accepted and broadcasts to every zone in
the unit, so a master entity is meaningful for control. It has no readable
state of its own, and `coordinator.py` mirrors the unit's first zone into
it.

| Fact | Status |
| --- | --- |
| `?10` returns six status frames, `?20`/`?30` return nothing when the unit is absent | Verified |
| `<10VO10` is accepted and broadcasts; `<17..`, `<27..`, `<99..` answer `Command Error.` | Verified |

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

`switch.py` still sends the command, in case other firmware honors it, and
reads the flag back; when it did not take, it raises rather than leaving a
switch that silently returns to off.

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

## Status response framing

| Fact | Status |
| --- | --- |
| A zone status response is framed as `` \r\n#>11...\r\n# `` | Verified |
| Reading it takes two reads: the first consumes the leading `` \r\n# `` marker, the second consumes the actual status record | Verified |

See `serial.py::_read_zone_status`.

## Baud rate change behavior

| Fact | Status |
| --- | --- |
| The amplifier switches to the new baud rate immediately after receiving the set-baud command and does not reply at the old rate | Verified |
| Waiting for a reply at the old rate after sending the command always times out | Verified |

See `api.py::MonopriceExtended.set_baud_rate`, which sends the command, then
switches the local port's rate, before querying zone 11 to confirm the amp
followed. `probe_baud_rate` only moves the local port and confirms zone 11,
so it never changes what the amplifier is set to.

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
