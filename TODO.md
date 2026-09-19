# TODO — findings from external Monoprice / clone implementations

Research-only when written. Items checked off have since been applied; the
rest are still flags for a human decision. Where an item contradicts a statement in
`docs/protocol.md` or behaviour in `custom_components/monoprice_custom/`,
the contradiction is named explicitly rather than silently "fixed".

Scope: the six sources the request named, read in full where reachable.
Current implementation read as of `198f408` (v2026.09.18.1).

## Sources

| # | Source | Reachable | What it is |
| --- | --- | --- | --- |
| S1 | [jnewland/mpr-6zhmaut-api](https://github.com/jnewland/mpr-6zhmaut-api) | Yes (README, `app.js`, `updateBaudRate.js`) | Node JSON API over the 10761 serial port |
| S2 | [martinezmp3 Hubitat driver](https://github.com/martinezmp3/Hubitat-Monoprice-6-zone-controller-TCP-IP-Serial/blob/master/Child-MonoPrice-6-Zone-Amp-Controller.groovy) | Yes | Hubitat child driver, serial-over-TCP |
| S3 | [openHAB `monopriceaudio` binding docs](https://v2.openhab.org/addons/bindings/monopriceaudio/) | Docs site blocked by egress proxy; read the same content from the binding's own `README.md` and Java source in `openhab/openhab-addons` | Multi-model binding |
| S4 | [openHAB community thread 1693 (page 3)](https://community.openhab.org/t/monoprice-6-zone-audio-amp-items-sitemap-rules/1693?page=3) | Yes (read 2026-09-19) | Items/sitemap/rules tutorial thread |
| S5 | [openHAB community thread 128924](https://community.openhab.org/t/monoprice-dayton-audio-xantech-whole-house-audio-binding-beta-3-2-0-4-0-0/128924) | Yes (read 2026-09-19) | Binding beta thread |
| S6 | [rsnodgrass/pyxantech](https://github.com/rsnodgrass/pyxantech) | Yes (README, `protocols/*.yaml`, `series/*.yaml`, `docs/dax88-rs232.txt`, `protocol.py`) | Multi-vendor Python RS-232 library |

- [x] **S4 and S5 have now been read (2026-09-19).** Both openHAB community
  URLs were blocked at the egress proxy when this file was written; they are
  reachable now and were fetched and compared against this file. **Neither adds
  anything new.** Every fact they carry was already reconstructed correctly
  from the binding's own README/source (S3):
  - S4's protocol detail is almost entirely the **31028 / PAM1270** (`!1PR1+\r`,
    `?1ZS+\r`, `#1ZS VO.. PO.. MU.. IS..+`, single-digit zones, no master),
    which D4 already records as a different, incompatible 70-volt unit. Its one
    general point, 300-600 ms between commands, is the same topic as B1, where
    S6 gives the better-sourced 400 ms to 50 ms history.
  - S5 yields the ser2net line `9600 8DATABITS NONE 1STOPBIT LOCAL` (already
    quoted verbatim in B8), the built-in serial-over-IP port 8080 (B8), and a
    5-60 s polling interval defaulting to 15 s (B2).

  No item in this file needed revising as a result.

---

## A. Contradictions with what the repository currently states

### A1. pyxantech's Monoprice status regex has the fields in the wrong order

`pyxantech/protocols/monoprice.yaml` parses a zone status as:

```
zone, power, source, mute, do_not_disturb(1 char), volume, treble, bass, balance, unknown, keypad
```

Every other source, including pyxantech's own `protocols/dax66.yaml`, uses:

```
zone, pa, power, mute, do_not_disturb, volume, treble, bass, balance, source, keypad
```

- S1's parser: `#>(zone)(pa)(pr)(mu)(dt)(vo)(tr)(bs)(bl)(ch)(ls)`.
- S3's `MONOPRICE_PATTERN` → `setZone/setPage/setPower/setMute/setDnd/setVolume/setTreble/setBass/setBalance/setSource/setKeypad`.
- S6's DAX88 manual excerpt (`docs/dax88-rs232.txt`): `>xxaabbccddeeffgghhiijj` where
  `aa:PA bb:Power cc:Mute dd:DT ee:Volume ff:Treble gg:Bass hh:Balance ii:Source jj:Keypad`.
- `pymonoprice.ZoneStatus`, which this integration relies on, matches the majority.

- [ ] **No change needed to our code — record that the divergence is
  pyxantech's bug, not ours**, so a future reader comparing the two does not
  "correct" `pymonoprice`'s ordering. Worth a line in `docs/protocol.md`'s
  status-framing section naming `pyxantech/protocols/monoprice.yaml` as an
  unreliable reference for field order (its `dnd` group is also 1 character
  wide, which misaligns every field after it).

### A2. `PA` being write-ignored is a documented hardware property of the whole family, not "this firmware"

`docs/protocol.md` ("PA is status only on this hardware") and
`switch.py::MonopricePASwitch.async_turn_on` both frame the write-ignore as a
single-unit observation, and `switch.py` still sends `<ZZPA01` "in case other
firmware honors it".

S3's README states it as a product fact across four models:

> On the 10761/DAX66/44519/44518 amplifiers, activating the 'Page All Zones'
> feature can only be done through the +12v trigger input on the back of the
> amplifier.

S3 models `page` as a read-only `Contact` channel and offers no page write at
all. S1 exposes `pa` on `GET` and `POST`, but never demonstrates a working
`POST`. S6 defines no PA command in any protocol YAML.

- [ ] Decide whether `MonopricePASwitch` should stay a `switch` that sends a
  command no known implementation believes will work, or become a read-only
  `binary_sensor` mirroring the +12V paging input. If it stays a switch,
  soften the "in case other firmware honors it" rationale — there is no
  firmware in any of these sources that honors it.
- [ ] Either way, document the +12V trigger input as the actual way to page,
  in `README.md` troubleshooting and `docs/protocol.md`. Users currently have
  no way to learn this from the repository.

### A3. `docs/protocol.md` is internally inconsistent about `?N0`'s frame count

The reply-framing table says `?10` produces **7** EOL frames ("one per zone");
the prose two sections later says "`?10` returns six status frames". Both can
be true (one leading marker frame + six records), but as written they read as
a contradiction. S1 corroborates six *records*: `queryControllers()` writes
`?<n>0\r` and polls until exactly `6 * i` zone objects have been parsed.

- [ ] Reword the table row so the marker frame and the six record frames are
  distinguished, and cross-reference the "one per zone" claim to the six.

### A4. Zone id 17/18 rejection is model-scoped, not protocol-scoped

`docs/protocol.md` records, as verified, that `<17..`, `<27..` and `<99..`
answer `Command Error.`. That is correct for the 10761, but S3 defines a
`monoprice8` thing type (Monoprice 44518) whose valid zone ids are
`11..18, 21..28, 31..38`, and a `monoprice4` type (44519) with `11..14` only.

- [ ] Re-scope that table row to "on the 10761 / 6-zone units", so the fact is
  not later read as a protocol invariant blocking 4-zone and 8-zone support.

---

## B. Gaps in the current implementation

### B1. No minimum interval between commands

S6 sets `min_time_between_commands: 0.05` on **every** series
(`monoprice6`, `dax66`, `dax88`, `xantech8`, `zpr68-10`, `sonance6`) and
enforces it in `protocol.py` with an explicit sleep, commented
"Enforce minimum time between RS232 commands to prevent timeouts."
Its README records the history: originally **400 ms**, reduced to 50 ms, with
a roadmap item to try 10 ms "if there are no bug reports of the 50 ms drop".

`gateway.py::_async_locked_call` serializes access but adds no spacing.
`coordinator.py::_async_update_data` issues a wake plus 6–18 back-to-back zone
queries every 5 seconds, and `media_player.py` follows every setter with an
immediate `async_refresh_zone`.

- [x] **Done.** `gateway.py::MIN_COMMAND_INTERVAL` is 0.05 s, held inside the
  I/O lock by `_async_hold_command_floor` and measured from when the previous
  command *finished*, so a slow command does not get a second delay stacked on
  it. A command that raised still spaces the next one. Measured on a 10761: a
  six-zone poll goes from 0.22 s to 0.47 s, well inside the 5 s interval.

### B2. Poll interval is hard-coded at 5 s, with no way to slow it down

`coordinator.py::UPDATE_INTERVAL = timedelta(seconds=5)`.

S3 exposes `pollingInterval` as **5–60 s, default 15**, plus
`disableKeypadPolling` for installations with no physical keypads (nothing
changes out-of-band, so there is nothing to poll for), and delays the first
poll by 10 s after startup (`INITIAL_POLLING_DELAY_SEC = 10`). S2 defines a
`pollSchedule()` method whose body is entirely commented out — i.e. that
driver ships with no polling at all.

- [ ] Consider a `pollingInterval` option (5–60 s) in the options flow.
- [ ] Consider a "no physical keypads" option that lengthens or suppresses
  routine polling, since keypad-driven changes are the only reason to poll.
- [ ] Note in `docs/design.md` why we poll at all: S3 states that *Xantech*
  amps emit unsolicited zone updates for keypad actions, and the Monoprice
  family does not. That asymmetry is the justification for our polling model
  and is not written down anywhere.

### B3. No `ignoreZones` equivalent for the master (broadcast) entities

`README.md` advertises master zones 10/20/30 that apply power, volume, source
and PA to all six zones at once, and `coordinator.py` mirrors zone `N1` into
`N0` for state.

S3 has `ignoreZones` — "A comma separated list of Zone numbers that will
ignore the 'All Zone' (**except All Off**) commands" — for zones that should
never be switched on or re-sourced by a broadcast (a bathroom, an outdoor
zone, a zone with no speakers attached). The all-off case is deliberately
exempt.

- [ ] Consider an `ignore_zones` option. Because `<N0..` broadcasts in the
  amplifier's own firmware, honouring an exclusion list means iterating zones
  instead of broadcasting — a real design decision, not a small change.

### B4. No volume guard on broadcast writes

S3 has `initialAllVolume` (1–30, default 10): "When 'All' zones are
activated, the volume will reset to this value to prevent excessive blaring of
sound". S2 clamps volume to a user-settable `MaxVolumen` (default 38).

`media_player.py` maps volume linearly onto `MAX_VOLUME = 38.0` with no cap,
and a master-zone volume write goes to six zones at once.

- [ ] Consider a maximum-volume option, and/or a reset-to-safe-level on
  master power-on. Six zones jumping to whatever the master was last set to is
  the failure mode S3 designed `initialAllVolume` around.

### B5. Zone and source counts are hard-coded to 6

`range(1, 7)` appears in `coordinator.py`, `media_player.py`, `sensor.py`,
`switch.py` and `config_flow.py::_zone_ids_for_units`; `api.py` has
`SOURCE_INDEXES = range(1, 7)`; `const.py` has `CONF_SOURCE_1..CONF_SOURCE_6`.

Same-protocol hardware with different counts (see §D): 44519 is 4 zones,
44518 is 8 zones, DAX88 is 8 zones **and 8 sources**, Xantech is 8 sources.

- [ ] If the integration is ever to cover more than the 10761 family, zone
  count and source count have to become per-entry configuration rather than
  constants. Flagging the extent of the change, not proposing it.

### B6. Expansion-unit discovery sends its probes back-to-back

`coordinator.py::_async_discover_active_units` and
`serial.py::_detect_expansion_units` query `?21` then `?31` with no delay, and
treat a timeout as "unit absent".

S1 spaces the equivalent startup queries by a full second:

```js
connection.write("?10\r");
if (AmpCount >= 2) { setTimeout(function(){ connection.write("?20\r"); }, 1000); }
if (AmpCount >= 3) { setTimeout(function(){ connection.write("?30\r"); }, 2000); }
```

S3 does not auto-detect at all — the user declares `numZones` in the thing
configuration.

- [x] **Spacing added.** `serial.py::EXPANSION_PROBE_SPACING` is 1.0 s,
  matching S1, and is waited out before each probe on both paths:
  `coordinator.py::_async_discover_active_units` and
  `serial.py::_detect_expansion_units`. Endpoint validation goes from 0.88 s to
  1.88 s on a single-unit amplifier, paid once at setup and at each
  rediscovery.
- [ ] **Still untested against expansion hardware.** Whether a slaved unit 2/3
  was ever actually missed by the old immediate probe cannot be confirmed here:
  the bench has **one** 10761 and no expansion units, so this path has still
  never been exercised against the hardware it exists for. The spacing above is
  a precaution taken on S1's precedent, not a fix validated against a
  reproduction. A false negative here silently removes 6 or 12 zones.

### B7. `Command Error.` is never detected as a desync signal

S1 treats it as unrecoverable: `if (data.startsWith('Command Error.')) process.exit(1)`.

`api.py::send_raw` drains after the first frame, and `rename_source` rejects
an out-of-range index before sending precisely because the error reply would
be misread as the next command's answer — so the repository already
understands the hazard, but only for the paths it controls. A `Command Error.`
arriving from any other cause (line noise, a partially written frame, a
foreign process on the port) leaves the buffer desynced with nothing watching
for it.

- [ ] Consider matching `Command Error.` in replies and forcing a buffer
  drain / `_link_ready = False` resync rather than parsing onward.

### B8. Serial-over-IP is supported but undocumented

`config_flow.py` accepts serial URLs (`_same_local_device` and
`canonicalize_endpoint` both have `"://"` branches), and `README.md` line 122
mentions "remote serial bridges" in passing. There is no setup guidance.

S3 ships exact recipes for both ser2net generations:

```text
# ser2net.conf (ser2net < 4)
8080:raw:0:/dev/ttyUSB0:9600 8DATABITS NONE 1STOPBIT LOCAL
```

```yaml
# ser2net.yaml (ser2net >= 4)
connection: &conMono
    accepter: tcp,8080
    enable: on
    options:
      kickolduser: true
    connector: serialdev,/dev/ttyUSB0,9600n81,local
```

S3 also notes newer amplifiers have a built-in Ethernet port speaking serial
over IP on port **8080**. S6 tested the DAX66 over RS232-over-IP with socat.
S1's author now recommends [`remserial`](https://github.com/jnewland/remserial)
plus the core Home Assistant integration in place of their own project.

- [ ] Add a serial-over-IP section to `README.md` with a `socket://host:port`
  example and one ser2net config.
- [x] Review what our baud machinery means over a bridge. `gateway.py::
  _ensure_link_sync` and `api.py::set_baud_rate` manipulate `self._port.baudrate`,
  which over `socket://` changes nothing on the far side of the bridge — the
  bridge's own fixed rate (`9600n81` above) wins. Either detect non-local
  endpoints and pin the target baud to whatever answers, or document that the
  baud option is meaningless for bridged endpoints. This is currently a silent
  mismatch.

### B9. Linux serial permissions are not in the troubleshooting section

S3's README: on Linux the port may fail to open until the service user is in
the `dialout` group (`usermod -a -G dialout <user>`), and two USB serial
adapters on one host can swap device nodes.

`README.md` already prefers `/dev/serial/by-id`, which addresses the second
half. The permission half is missing, and `serial.py::_PORT_ERRORS` catches
`PermissionError` into a generic "cannot connect".

- [ ] Add `dialout` guidance to `README.md` troubleshooting, and consider a
  distinct config-flow error string for `PermissionError` so the user is told
  which of the two problems they have.

---

## C. Edge cases and troubleshooting worth capturing

- [x] **Baud resets to 9600 on power loss, and a 30-second power-off is the
  documented way to force it.** S1: "By default, at power loss, the device is
  set to run at 9600 BAUD" and "To reset the baud rate remove power from the
  controller for 30 seconds - it will reset to 9600 BAUD". Our
  `POWER_ON_BAUD_RATE` constant encodes the first half; neither half is in
  `README.md` where a user stuck at the wrong rate would look.
- [x] **Connecting at the wrong baud rate does not lock the controller.**
  S1: "Running `npm run-script baudrate` with the incorrect connection baud
  rate will not cause it to lock so initialization scripting could be created
  to reset the baudrate before the API enables." This is a useful reassurance
  for `gateway.py`'s probe loop, which walks all six rates — worth stating in
  `docs/protocol.md` that the probe is safe by design, not merely by luck.
- [x] **Six supported baud rates are confirmed by an independent source.**
  S1's `updateBaudRate.js` validates against exactly
  `[9600, 19200, 38400, 57600, 115200, 230400]`, matching
  `serial.py::SUPPORTED_BAUD_RATES`. Record the corroboration.
- [ ] **Writes to a powered-off zone are silently discarded.** This is our own
  hardware finding and **no other source mentions it** — not S1, S2, S3 or S6.
  Flagging that it is unique to this repository's documentation and therefore
  unconfirmed elsewhere, rather than contradicted.
- [ ] **Keypad status is read-only.** S1 accepts `ls` on `GET /zones/:zone/:attribute`
  but deliberately omits it from the `POST` list. S3 models it as a `Contact`.
  `sensor.py::MonopriceKeypadSensor` already matches. The DAX88 manual gives
  the encoding explicitly: `jj: Keypad Connection status (00: Not connected,
  01: Connected)`.
- [ ] **Balance/tone display conventions agree across implementations.**
  S3 uses `minTone=-7, maxTone=+7, toneOffset=7` and `minBal=-10, maxBal=+10,
  balOffset=10` for the Monoprice family, which is exactly the 0–14 and 0–20
  wire ranges `number.py` translates. Record the independent confirmation in
  `docs/protocol.md`'s EQ table.
- [ ] **S2 parses status by fixed byte offsets**, not by regex
  (power at 7–9, mute 9–11, volume 13–15, treble 15–17, bass 17–19, balance
  19–21, source 21–23). It skips the `pa` and `dt` fields entirely. Mentioned
  only as evidence of the field widths; it is the least reliable of the
  sources and should not be used to settle anything.

---

## D. Vendor and model support

Several vendors ship hardware that speaks a command set matching, or nearly
matching, what this integration already sends. None of it is supported today
(the integration hard-codes 6 zones, 6 sources, the `#` response prefix and
the `\r\n#` EOL), but the distance varies a lot by model.

### D1. Drop-in matches — same protocol, same limits, same zone ids

| Vendor | Model | Evidence | Divergence from our implementation |
| --- | --- | --- | --- |
| Monoprice | MPR-SG6Z / **10761** | S1, S3, S6 (`monoprice6`) | None — this is the target device |
| Monoprice | **39261** "Passive Matrix" | S3 (uses the `amplifier` thing id) | None claimed by S3 |
| Dayton Audio | **DAX66** | S3 (`amplifier` thing id, tested); S6 `series/dax66.yaml` | **See D2** — S6 found a reply-framing difference |
| Soundavo | **WS66i** | S6 README: "an updated version of the Monoprice 10761… should use the `monoprice6` integration when RS232 controlled" | Adds IP/telnet control we do not speak (see [pyws66i](https://github.com/ssaenger/pyws66i)) |
| McLELLAND, Factor, others | unnamed clones | S3: "Compatible clones from McLELLAND, Factor, Soundavo, etc. should work as well" | Unverified |

Command-level convergence for all of the above, against `api.py` and `pymonoprice`:

| Command | Ours | S1 | S3 | S6 | Agrees |
| --- | --- | --- | --- | --- | --- |
| Zone status | `?{zone}` | `?{zone}` | `?` + zone | `?{zone}` | Yes |
| Power | `<{zone}PR{00,01}` | same | `PR` | same | Yes |
| Mute | `<{zone}MU{00,01}` | same | `MU` | same | Yes |
| Volume | `<{zone}VO{00-38}` | same | `VO`, max 38 | same | Yes |
| Treble | `<{zone}TR{00-14}` | same | `TR`, −7..+7 | same | Yes |
| Bass | `<{zone}BS{00-14}` | same | `BS`, −7..+7 | same | Yes |
| Balance | `<{zone}BL{00-20}` | same | `BL`, −10..+10 | same | Yes |
| Source | `<{zone}CH{01-06}` | same | `CH` | same | Yes |
| DND | `<{zone}DT{00,01}` | same | `DT` | *not defined* | S6 has no DND |
| PA | `<{zone}PA{00,01}` | `POST .../pa` | *read-only* | *not defined* | **No — see A2** |
| Rename source / welcome | `1<NAME   `, `M<NAME   ` | *absent* | *absent* | *absent* | **Ours only** |
| Set baud | `<{baud}` | `<{baud}` | *absent* | *absent* | Ours + S1 |
| Zone ids | `11–16, 21–26, 31–36` | same | same | same | Yes |
| Reply prefix | `#>` | `#>` | `#>` | `#>` | Yes |

Two capabilities in `api.py` — keypad source renaming / welcome message, and
the baud-rate switch — appear in **no** other implementation except the baud
switch in S1. Worth noting as a genuine differentiator, and as a reason our
`docs/protocol.md` is the only written record of the rename framing.

- [ ] If a "supported hardware" section is ever added to `README.md`, the
  39261, DAX66, WS66i and generic-clone rows above are the defensible list.

### D2. Same commands, different reply framing — would break our reader

**Dayton Audio DAX66.** S6's `protocols/dax66.yaml` splits the DAX66 out of
the shared `monoprice` protocol solely over line endings, with the reasons in
inline comments:

```yaml
  format:
    command:
      separator: ""        # <<< do NOT insert '#'
    response:
      eol: "\n"            # <<< read until LF to consume the device's \r\r\n
      separator: ""        # <<< don't expect a '#'
  response_eol: "\n"       # <<< critical: consume full \r\r\n line
```

It also sets `zone_status_skip: 1` and a regex tolerating an optional `#`.
This directly contradicts S3, which puts the DAX66 on the same `#>` prefix as
the 10761 — so either the two units differ by firmware revision, or one of the
two projects is wrong.

`serial.py::_read_zone_status` reads `read_until(b"\r\n#", ...)` twice, and
`api.py::REPLY_EOLS` assumes the `#`-delimited framing throughout. On a DAX66
matching S6's description, both reads would time out and the config flow would
report "not a Monoprice amplifier".

- [ ] Flagged, not fixed: any future DAX66 support needs the EOL to be
  per-model, not a module constant. Do not claim DAX66 support until this is
  resolved against real hardware.

**Dayton Audio DAX88.** S3's `DAX88` enum and S6's `docs/dax88-rs232.txt`
(the vendor manual) agree: response prefix is `>` with **no** leading `#`
(S3's comment: "DAX88 status string is the same but does not have leading
'#'"). Field order is identical to the 10761.

### D3. Same command set, different zone/source counts

| Vendor | Model | Zones | Sources | Zone ids | Notes |
| --- | --- | --- | --- | --- | --- |
| Monoprice | 44519 | 4 | 6 | `11–14, 21–24, 31–34` | S3 `monoprice4`, untested |
| Monoprice | 44518 | 8 | 6 | `11–18, 21–28, 31–38` | S3 `monoprice8`, untested |
| Dayton Audio | DAX88 | 8 (2 un-amplified) | 8 | **`01–08`** — single digit, not linkable | Tone range `00–24` = **−12..+12**, not −7..+7 |

The DAX88 is the interesting one: identical verbs, identical field order,
but single-digit zone ids, double the tone range, and eight sources. Our
`api.py::SOURCE_INDEXES` and `services.py`'s `vol.Range(min=0, max=14)`
schemas would all reject valid DAX88 values.

### D4. Related but incompatible — same vendor lineage, different protocol

| Vendor | Model | Series | Why it will not work |
| --- | --- | --- | --- |
| Monoprice / OSD Audio | 31028 / PAM1270 | S3 `monoprice70` | 70-volt line. Command prefix `!`, suffix `+\r`, query suffix `ZS`. Status reads `?6ZS VO8 PO1 MU0 IS0+`. No treble/bass/balance in the status frame; 2 sources; source verb is `IS`, balance is `BA`; no DND |
| Xantech | MRC88/MRC88m, MX88/MX88vi, MX88a/MX88ai, MRAUDIO8X8/8X8m, CM8X8/CM8X8DR | S3 `xantech`, S6 `xantech8` | Prefix `!`, suffix `+\r`, query suffix `ZD`, response prefix `#`. Status reads `#1ZS PR0 SS1 VO0 MU1 TR7 BS7 BA32 LS0 PS0+`. Single-digit zones 1–16, 8 sources, source verb `SS`, balance 0–63 (offset 32). Emits **unsolicited** keypad updates |
| Xantech | ZPR68 / ZPR68-10 | S6 `zpr68-10` | 6 zones / 8 sources, **no balance command at all**, tone ±12, `zone_status_skip: 2` |
| Sonance | C4630 SE, 875D SE, 875D MKII | S6 `sonance6` | **19200 baud**, 4 sources, volume 0–60, tone 0–8, balance 0–10 |
| Xantech | MRAUDIO4X4, BXAUDIO4x4, MRC44, MRC44CTL | S6 README | IR control only — no serial control exists |

S6's README records the lineage that explains the family resemblance:

> The Monoprice MPR-SG6Z and Dayton Audio DAX66 appear to have licensed or
> copied the serial interface from Xantech. Both Monoprice and Dayton Audio
> use a version of the Xantech multi-zone controller protocol.

- [ ] Decide and write down a scope statement: this integration targets the
  Monoprice 10761 family (D1) and nothing else. Without one, the resemblance
  above invites bug reports from DAX88/Xantech owners whose hardware was never
  in scope.

### D5. Xantech cabling gotcha (for the scope statement's "why not")

S6 documents that MX88/MX88ai rear COM ports are HD15, not DB9, need Xantech
adapter cable PN 05913665 whose **published pinout is wrong** (S6 publishes a
corrected table), and are already wired null-modem so no null-modem cable
should be added. The front DB9/USB ports cannot control the unit at all.
Baud also varies by model within the same series: MRC88m 19200, MX88/MX88a/
MX88ai 57600, the rest 9600.

- [ ] Nothing to do unless Xantech support is ever attempted; recorded so the
  cost is visible if it is.

---

## E. Cross-source agreement on serial line settings

All four sources agree, and this matches `serial.py`'s
`serial_for_url(..., byte_size=8, parity=NONE, stopbits=ONE)`:

| Setting | Value | S1 | S3 | S6 | DAX88 manual |
| --- | --- | --- | --- | --- | --- |
| Baud (default) | 9600 | Yes | Yes | Yes | Yes |
| Data bits | 8 | Yes | Yes | Yes | Yes |
| Stop bits | 1 | Yes | Yes | Yes | Yes |
| Parity | None | Yes | Yes | Yes | Yes |
| Flow control | None / local | — | `LOCAL` | — | None |
| Command terminator | `\r` (0x0D) | Yes | Yes | Yes | "required" |

- [ ] One thing we do not set: **flow control**. S3's ser2net examples pass
  `LOCAL` (no hardware flow control) explicitly, and the DAX88 manual states
  "Flow Control: None". `serial.py` leaves `rtscts`/`xonxoff` at whatever
  `serialx` defaults to. Confirm the default is off; if the default ever
  changes, a hardware-handshake-expecting port would hang with no diagnostic.
