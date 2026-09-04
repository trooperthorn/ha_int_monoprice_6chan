# RS-232 protocol notes

Facts about the Monoprice 6-zone amplifier's RS-232 protocol that the code
relies on but does not restate inline. "Verified" means observed against
real hardware or documented in the RS-232 spec and pymonoprice's
`ZoneStatus`; "unverified" means inferred from behavior and not confirmed
against the vendor spec.

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
followed.

## EQ and balance wire ranges

| Control | Wire range | Display mapping | Status |
| --- | --- | --- | --- |
| Bass (BS) | 0-14 | Signed dB: 0 = -7dB, 14 = +7dB | Verified (RS-232 spec, pymonoprice `ZoneStatus`) |
| Treble (TR) | 0-14 | Signed dB: 0 = -7dB, 14 = +7dB | Verified (RS-232 spec, pymonoprice `ZoneStatus`) |
| Balance | 0-20 | 0 = full left, 10 = center, 20 = full right | Verified (RS-232 spec) |

`number.py` displays the translated signed value to the user and translates
back to the 0-14/0-20 wire value before sending. `const.py`'s
`ATTR_BALANCE`/`ATTR_BASS`/`ATTR_TREBLE` service fields carry the raw wire
value, not the display value.

## Keypad commands

| Command | Effect | Status |
| --- | --- | --- |
| `M` | Sets the keypad's boot welcome message | Verified |
| A source number (1-6) | Renames that source's label on the keypad | Verified |

See `text.py::MonopriceKeypadText`.
