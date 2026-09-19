# Home Assistant Custom Integration: Monoprice 6-Zone Amplifier

[![GitHub Release](https://img.shields.io/github/v/release/trooperthorn/ha_int_monoprice_6chan?style=for-the-badge)](https://github.com/trooperthorn/ha_int_monoprice_6chan/releases)
[![GitHub Activity](https://img.shields.io/github/commit-activity/m/trooperthorn/ha_int_monoprice_6chan?style=for-the-badge)](https://github.com/trooperthorn/ha_int_monoprice_6chan/commits/master)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)



A high-performance, completely rewritten Custom Integration for the Monoprice 6-Zone Amplifier (and compatible clones). This expands massively on the core Home Assistant integration by introducing high-speed serial communication, dynamic hardware discovery, and complete control over EQ, Public Address (PA), and Do Not Disturb (DND) modes.

See [docs/README.md](docs/README.md) for design rationale, protocol notes, and release/security controls.

## ✨ USB Serial Configuration
![Control UI Screenshots](https://github.com/trooperthorn/ha_int_monoprice_6chan/blob/main/Screenshots/usb-config.png?raw=true)


## Media Player with PA and Do Not Disturb

![Control UI Screenshots](https://github.com/trooperthorn/ha_int_monoprice_6chan/blob/main/Screenshots/control-ui.png?raw=true)

## Main Media Player Activates all Players, syncs Power and Source Control

![Control UI Screenshots](https://github.com/trooperthorn/ha_int_monoprice_6chan/blob/main/Screenshots/main-ui.png?raw=true)

---

## ✨ Key Features & Upgrades

This integration has been rebuilt around a modern, non-blocking `DataUpdateCoordinator` architecture to provide lightning-fast, highly reliable control:

*   🚀 **High-Speed Serial Auto-Negotiation:** The integration automatically detects the amplifier's current baud rate and negotiates it up to a **configurable target rate** (see [Baud Rate & Latency](#-baud-rate--latency)), cutting command latency for snappier UI responses. Each zone action also triggers a targeted single-zone refresh instead of waiting for the next full poll.
*   🧠 **Smart Hardware Auto-Discovery:** No more 24-second timeout lags. The integration automatically probes for expansion units (Units 2 and 3) on boot. If they aren't physically connected, it skips polling them entirely.
*   🎛️ **Master Unit Controls:** Full support for Master Zones (10, 20, 30). Adjusting power, volume, source, or PA on a Master Zone instantly applies the change to all 6 zones on that unit simultaneously. *(Enabled by default)*
*   🎙️ **Public Address & DND Switches:** PA and Do Not Disturb are now fully Writable Switches (not just read-only sensors). Toggle PA on a zone to instantly force it to Source 1 for announcements.
*   🛡️ **Persistent USB Protection:** The config flow automatically maps volatile `/dev/ttyUSBx` paths to their permanent `/dev/serial/by-id/` symlinks to prevent port collisions with other serial devices on host reboots.

---

## 🎚️ Included Entities

For every active zone detected, this integration generates the following controls:

### Media Players
*   **Zone Media Player:** Standard control (Power, Volume, Mute, Source Selection).
*   **Sound Modes:** Selectable via the media player dropdown (`Normal`, `High Bass`, `Medium Bass`, `Low Bass`).

### Switches
*   **Public Address (PA):** Toggling ON forces the zone to Source 1 (usually a paging mic or TTS cast device) and overrides normal audio.
*   **Do Not Disturb (DND):** Toggling ON isolates the zone from Master Zone commands (like house-wide power off or volume changes).

### Number Sliders (EQ)
*   **Balance:** Left/Right speaker balance (-10 full left to +10 full right, 0 = center)
*   **Bass:** Low-frequency EQ (-7dB to +7dB)
*   **Treble:** High-frequency EQ (-7dB to +7dB)

### Text
*   **Source 1-6 Display Name:** Renames the source label shown on physical zone keypads (8 ASCII characters max).
*   **Keypad Welcome Message:** Sets the boot message shown on zone keypads (8 ASCII characters max).

### Remote
*   **RS232 Controller:** Sends any raw command from the [RS-232 spec](#-rs-232-protocol-coverage) directly, for commands not otherwise exposed as an entity. Also exposes the `set_baud_rate` action.

### Diagnostics

*   **Connection** (`binary_sensor`) - whether the amplifier is answering. Unlike
    every other entity here it stays readable while the amplifier is down, so it
    reports `Disconnected` rather than going unavailable, and can be used as an
    automation trigger. Its attributes carry the outage history: when contact was
    lost, how long the last outage lasted, how many there have been, the current
    and detected link speeds, and how long until the next retry.
*   **Link speed** (`sensor`) - the rate the serial link is actually running at,
    in baud.
*   **Last disconnected** (`sensor`) - a timestamp, so Home Assistant renders it
    as "x minutes ago" and it can be graphed against other events.

### Sensors
*   **Keypad Status (diagnostic):** Read-only, shows if the physical wall keypad for the zone is `Connected` or `Disconnected`.

---

## 📡 RS-232 Protocol Coverage

Every command documented in the Monoprice Multizone Controller RS-232 spec is reachable, either as a dedicated entity/action or via the raw `remote.RS232 Controller` entity:

| Command | Exposed as |
| :--- | :--- |
| `PR` power | Media player power |
| `MU` mute | Media player mute |
| `VO` volume | Media player volume |
| `TR`/`BS` treble/bass | Number entities (dB) |
| `BL` balance | Number entity |
| `CH` source | Media player source select |
| `PA` paging | Switch |
| `DT` do-not-disturb | Switch |
| `1`-`6<name>` source rename | Text entities |
| `M<name>` keypad welcome message | Text entity |
| `<BAUD` link speed | `remote.set_baud_rate` action / options flow |
| `?xx` full zone status | Polled by the coordinator |
| `?xxPP` single-field status | `api.zone_field_status()` (available for automations/future targeted polling) |

---

## ⚙️ Installation

### Option 1: HACS (Recommended)
1. Open **HACS** -> **Integrations** -> **3 Dots (Top Right)** -> **Custom repositories**
2. Add this repository URL: `https://github.com/trooperthorn/ha_int_monoprice_6chan` (Category: Integration)
3. Click on the newly added **Monoprice 6-Zone Home Audio Controller** and click **Download**.
4. Restart Home Assistant.
5. Go to **Settings** -> **Devices & Services** -> **Add Integration** and search for **Monoprice 6-Zone Amplifier Custom**.

### Option 2: Manual
1. Copy the `monoprice_custom` folder from this repository into your `/config/custom_components` directory.
2. Restart Home Assistant.
3. Go to **Settings** -> **Devices & Services** -> **Add Integration** and search for **Monoprice 6-Zone Amplifier Custom**.

> **Legacy-domain migration:** Releases through `2026.08.20` registered as
> `monoprice`, the same immutable domain as Home Assistant Core. There is no
> safe automatic way to distinguish and take over those entries. Disable the
> existing `monoprice` entry first, restart Home Assistant, then add this
> integration as `monoprice_custom`. Delete the legacy entry only after the
> new entry and automations have been verified. Never leave both entries
> enabled against the same serial interface.

---

## 🔌 Configuration Best Practices

The supported setup path is three steps, in this order, on purpose: you cannot
name a zone until the integration knows the zone exists, and it cannot know
that until the amplifier has actually answered a status query.

`Connect via USB / Serial -> Verify Monoprice amplifier -> Configure amplifier -> Name each zone's media player -> Complete`

* **Connect via USB / Serial:** Uses Home Assistant's native serial-port selector, the same step Davis Vantage and Elk-M1 use. Manual paths and serial URLs remain available for containers and remote serial bridges. Opening the form does not open a port; only the submitted port is probed, and only after the verify step is confirmed. On Linux, `/dev/serial/by-id` is preferred, with `/dev/serial/by-path` as a fallback. Windows `COM*` paths remain supported.
* **Verify Monoprice amplifier:** Opens only the selected port, asks the amplifier for its zone 11 status while detecting the baud rate, then probes for a second and third expansion unit before closing the port. If the probe fails, the selector is shown again with the reason so you can pick the port again or choose a different one without restarting the flow.
* **Configure amplifier:** Owns source names and the target link speed. The port, adapter identity, and detected baud remain config-entry data.
* **Name each zone's media player:** One optional field per zone actually detected in the previous step (6, 12, or 18 fields, depending on how many expansion units answered). A blank field keeps that zone's default `Zone N` name. **The amplifier itself has no way to store a room name** - unlike the source names above, which the keypad displays, a zone label only ever exists in Home Assistant - so this step, and the matching one under **Configure**, are the only places it's set.

If you are using a multi-port USB-to-Serial adapter (like a 4-port FTDI cable), **always select the path starting with `/dev/serial/by-id/...`**. 
Linux frequently reassigns basic `/dev/ttyUSB0` paths when your server reboots. Using the `by-id` path guarantees the integration will always find the amplifier, even if you move the USB cable to a different port on your host machine.

---

## 🛠️ Custom Services

This integration exposes custom services for advanced automation workflows:

| Service | Description |
| :--- | :--- |
| `monoprice_custom.snapshot` | Saves the current power, volume, and source state of a zone. Perfect for saving state before an automated TTS announcement. |
| `monoprice_custom.restore` | Restores a zone to its previously snapshotted state. |
| `monoprice_custom.set_balance` | Set the balance integer via automation. |
| `monoprice_custom.set_bass` | Set the bass integer via automation. |
| `monoprice_custom.set_treble` | Set the treble integer via automation. |
| `monoprice_custom.set_baud_rate` | Negotiate the amplifier and local port to a new link speed (9600/19200/38400/57600/115200/230400). |

---

## 🚦 Baud Rate & Latency

> ### ⚡ The amplifier's default baud rate is **9600**
>
> **If the amplifier has stopped responding and you suspect the link speed,
> unplug it from mains power, wait 30 seconds, and plug it back in.** That
> resets the RS-232 link speed to 9600 baud, which is where this integration
> always starts looking. You do not need to change anything in Home Assistant
> first, and you cannot damage anything by trying it.

The amplifier powers on at **9600 baud** every time and keeps whatever rate it
was last told to use only until it loses power. The setting you choose under
**Settings → Devices & Services → Monoprice → Configure** is called
**Preferred maximum link speed**, and the word *maximum* is the important one:
it is the speed to work up to, not the speed the connection starts at.

### Why it is a ceiling and not just a setting

The amplifier changes speed the moment it receives the command and never
acknowledges it. So if you pick a speed your cabling cannot carry, the
amplifier switches anyway and is then unreachable, and **you cannot tell it to
go back** because it can no longer understand you. The only way out is to
remove its power for 30 seconds.

That is why **Let the integration work up to it automatically** is on by
default. With it enabled the integration:

- raises the speed **one step at a time**, confirming each one before going
  further, so a speed that does not work costs you one step rather than a dead
  link;
- **remembers the highest speed that worked** on your cabling and returns
  straight to it after a power cycle, instead of climbing again;
- **never retries a speed that failed**, so one bad experience is not repeated
  every time the amplifier restarts;
- if a switch is not confirmed, **goes looking for the amplifier** at every
  supported speed before giving up, because an unconfirmed switch is often just
  an unlucky reply rather than a dead link.

Turn it off and the integration switches straight to the speed you picked, with
the consequence above. The `set_baud_rate` service always goes directly to the
speed you name, whatever this checkbox says, because naming a speed explicitly
means you want that speed.

A higher speed lowers per-command latency but is less tolerant of long or noisy
RS-232 runs. The **Link speed** diagnostic sensor shows what the connection is
actually running at, which will differ from your preferred maximum while it is
still working its way up, or if it settled lower.

### Recovering the link by hand

You should rarely need this, because the integration re-probes all six
supported rates (9600, 19200, 38400, 57600, 115200, 230400) whenever it loses
contact. Connecting at the wrong rate is documented not to lock the controller
or put it into a bad state, which is what makes that sweep safe. But if you
want to force a known-good starting point:

1. **Remove power from the amplifier for a full 30 seconds.** A quick
   off-and-on may not be enough; the controller has to fully discharge.
2. Power it back on and give it about **10 seconds**. Measured on a 10761,
   RS-232 starts answering roughly 8 seconds after power returns. It is now at
   **9600 baud**.
3. In Home Assistant, set the target link speed to **9600** under
   **Configure**, so the integration does not immediately negotiate away from
   the rate you just restored while you are diagnosing.
4. Reload the integration, or wait for the next poll. It re-probes
   automatically and will find the amplifier.

Once it is back online you can raise the target link speed again if you want
the lower latency.

**Why this happens at all.** The amplifier switches rate the instant it
receives the command and never acknowledges it, so a switch that is not
confirmed can leave the amplifier at the new rate while Home Assistant is
still listening at the old one. The integration handles that by sweeping every
supported rate on the next poll, so this is a recovery path of last resort
rather than something you should expect to use.

> **Serial-over-IP users:** the target link speed only changes the *local* end
> of the connection. The bridge's own configured rate governs the wire to the
> amplifier, so a power-cycle reset puts the amplifier back to 9600 and your
> bridge must be set to 9600 too. See [Serial over IP](#-serial-over-ip).

---

## 🌐 Serial over IP

The port field accepts a `socket://host:port` URL as well as a local device, so
the amplifier does not have to be plugged into the Home Assistant machine.
Newer amplifiers ship an Ethernet port that speaks serial over IP directly on
port **8080**; for everything else, a small bridge next to the amp works.

```text
socket://192.168.1.50:8080
```

`ser2net` is the usual bridge. Version 4 and later uses YAML:

```yaml
connection: &conMono
    accepter: tcp,8080
    enable: on
    options:
      kickolduser: true
    connector: serialdev,/dev/ttyUSB0,9600n81,local
```

Older `ser2net.conf` syntax:

```text
8080:raw:0:/dev/ttyUSB0:9600 8DATABITS NONE 1STOPBIT LOCAL
```

Two things to know about bridged setups. The **target link speed only changes
the local end** - the bridge's own configured rate governs the wire to the
amplifier, so set them to match at the bridge and leave the integration at the
same value. And `kickolduser` matters: without it a stale connection can hold
the port and the integration will report "cannot connect".

---

## 🔁 Reconfiguring

If you move the amplifier to a different USB/serial port, use **Settings → Devices & Services → Monoprice → Reconfigure** instead of removing and re-adding the integration, it keeps your existing entities, automations, and history intact. Reconfigure uses the same selector and verifier as setup; when the adapter exposes a stable USB identity, a different adapter is rejected, and a failed probe leaves the existing entry untouched.

**Why removing and re-adding is not equivalent.** Every entity's id here is built from this specific config entry's own internal id plus the zone number - the standard, correct way a Home Assistant integration builds entity ids, and the same approach Davis Vantage and Elk-M1 use. That id only lives as long as one config entry does. Removing the integration deletes that entry, and Home Assistant deletes its entity-registry rows - your renamed zones included - along with it; a fresh "Add Integration" afterward creates a brand-new entry with a brand-new internal id, so even reusing the exact same zone names produces entities with different ids than before. Reconfigure edits the same entry in place, so nothing is ever deleted.

**Renaming a zone without touching the port.** If only a zone's name needs to change - no port or amplifier involved - use **Settings → Devices & Services → Monoprice → Configure** instead of Reconfigure. It asks for source names and target baud, then the same zone-name step described above, pre-filled with whatever is already set, without probing the serial port at all.

---

## 🎛️ Behaviour Options

All of these live in **Settings → Devices & Services → Monoprice → Configure**,
alongside the source names and target link speed.

| Option | Range | Default | What it does |
| --- | --- | --- | --- |
| **Preferred maximum link speed** | 9600-230400 | 9600 | The speed to work up to, not the one the connection starts at. See [Baud Rate & Latency](#-baud-rate--latency). |
| **Let the integration work up to it automatically** | on/off | on | Climb one step at a time, remember what worked, never retry what failed. Turning it off switches straight to the chosen speed, which can strand the link until the amplifier is power cycled. |
| **Poll interval** | 5-60 s | 5 s | How often every zone is re-read. The amplifier never reports changes on its own, so this is the only way a keypad or front-panel change reaches Home Assistant. Raise it to put less traffic on a shared or bridged line. This interval applies while the amplifier is answering; once it stops, retries back off automatically (5s, 10s, 20s ... up to 2 minutes) so a powered-off amplifier is not swept continuously, and reset to normal on the first success. Each zone has a diagnostic **Keypad status** sensor: if every zone reads `disconnected`, keypad presses are not something you need to catch and a longer interval costs you little (the front panel still changes state out of band). |
| **Maximum volume** | 1-38 | 38 | Ceiling applied to every volume this integration sends, including master writes. Useful where the wire maximum is more than the speakers should take. |
| **Volume on master power-on** | 0-38 | 0 (off) | When a master zone is switched on, force every zone it reaches to this volume first. Guards against six zones jumping to whatever the master was last set to. |
| **Zones excluded from master commands** | any zones | none | Zones a master (all-zone) command must skip - a bathroom, an outdoor zone, a zone with no speakers. **Turning everything off is deliberately exempt** and still reaches every zone. |

Excluding any zone changes how a master command is sent: with nothing excluded
the amplifier's own broadcast is used, one command for the whole unit, and with
an exclusion list the remaining zones are addressed one at a time, because the
broadcast happens inside the amplifier's firmware and cannot be filtered.

---

## ⚠️ Known Limitations

*   **Supported hardware is the Monoprice 10761 six-zone family** (and the units that match it exactly: Dayton DAX66, Monoprice 39261, Soundavo WS66i and the generic clones). Four-zone and eight-zone relatives such as the Monoprice 44519/44518 and the Dayton DAX88 speak the same commands but have different zone and source counts, which this integration hard-codes to six. The Monoprice 31028/PAM1270 and Xantech controllers use a different framing altogether and will not work. See `docs/decisions.md`.

*   Paging is a hardware function. The `Public Address` switch sends the documented `<ZZPA01` command, but the amplifier ignores it: on this family, "Page All Zones" can only be activated through the **+12V trigger input** on the back of the amplifier. Route your announcement device's audio into the PA input and drive that trigger. The switch is kept because the command is accepted without error, so a firmware that does honour it would work, and it now raises an error rather than silently flipping back.
*   **Volume, mute, source and tone changes only apply while a zone is powered on.** Sent to a zone that is off, the amplifier acknowledges them normally and discards them, with no error of any kind. Power and Do Not Disturb are the exceptions. Turn the zone on first. See [Troubleshooting](#a-control-changed-and-then-snapped-back).
*   The amplifier does not range-check values sent through the `remote` entity's raw commands; `<11VO99` is accepted without complaint. The normal entities clamp for you, raw commands do not.
*   The `Sound Mode` dropdown on each zone media player is a convenience preset that just sets the zone's Bass value, it isn't a hardware DSP mode, and it will move the Bass number entity's slider when used.
*   Source names/keypad messages are limited to 8 ASCII characters by the hardware; longer input is truncated, and non-ASCII input is rejected with an error rather than sent as mangled bytes.
*   Neither the source names nor the keypad welcome message can be read back over RS-232, so those text entities show the last value this integration sent, not what the keypad displays.

## 🩺 Troubleshooting

### The amplifier is not responding at all

*   **First, try the power-cycle reset.** Unplug the amplifier for **30
    seconds** and plug it back in. It returns to **9600 baud**, the rate this
    integration always probes first. Full steps in
    [Baud Rate & Latency](#-baud-rate--latency).
*   **"Cannot connect" during verification:** confirm that no other integration
    or process owns the selected interface. Only the submitted interface is
    opened, and the verifier closes it before setup continues. On a
    serial-over-IP bridge, a stale TCP session can hold the port; set
    `kickolduser: true` in `ser2net`.
*   **"Not allowed to open that port":** a permissions problem rather than a
    wiring one. On a Linux host the user Home Assistant runs as needs to be in
    the `dialout` group (`sudo usermod -a -G dialout <user>`, then restart), and
    on Home Assistant OS the port must be passed through to the container. This
    is reported separately from "cannot connect" so you know which of the two
    you have.
*   **"Not a Monoprice amplifier" during verification:** the interface opened
    successfully but did not return a structurally valid Zone 11 response at any
    supported baud rate. Check that the cable is a straight-through serial cable
    on the amplifier's **control** port, and that the amplifier is powered.
*   **Entities go `Unavailable` intermittently:** usually a baud-rate mismatch
    on a long or noisy cable run. Lower the target link speed in **Configure**,
    one notch at a time.
*   **Nothing responds after changing the target link speed:** the amplifier
    switches rate on receipt and never acknowledges, so it can end up somewhere
    the integration is not. It re-probes every supported rate on the next poll
    and connecting at the wrong rate cannot lock the controller, so this
    normally clears itself. If it does not, use the 30-second power-cycle reset
    above.
*   **An expansion unit is unavailable:** discovery retries after recovery and
    every five minutes. A newly detected unit is added dynamically; an existing
    unit that returns becomes available again without a restart.

### A control changed and then snapped back

*   **The zone was off.** This is the single most common surprise with this
    hardware. The amplifier accepts volume, mute, source, treble, bass and
    balance commands for a powered-off zone with a perfectly normal
    acknowledgement, and then discards them. There is no error to report.
    **Turn the zone on first, then set the value.** Power and Do Not Disturb are
    the exceptions; they apply whether the zone is on or off.

    Home Assistant re-reads the zone after every write, so the entity shows what
    the amplifier actually kept rather than what you asked for. That is why the
    slider springs back instead of silently lying to you.
*   **You hit the volume ceiling.** If a **Maximum volume** is set under
    **Configure**, every volume this integration sends is clamped to it,
    including master writes. A slider dragged above the ceiling lands on it.
*   **The zone is excluded from master commands.** Zones listed under **Zones
    excluded from master commands** ignore all-zone power, volume, source and
    tone writes. Turning everything *off* deliberately still reaches them.
*   **The `Public Address` switch will not stay on.** Paging is a hardware
    function on this family: it can only be activated through the **+12V trigger
    input** on the back of the amplifier. The switch sends the documented
    command, reads the flag back, and raises an error when the amplifier ignores
    it, which it will. See Known Limitations.

### Was it the power, or the serial cable?

These look the same from Home Assistant, but the fix is completely different.
The integration tells them apart automatically and reports which it thinks it
was in the **Connection** sensor's `last_outage_cause` attribute and in the
diagnostics download.

It works because losing power resets the amplifier's link speed to 9600 while a
cable problem does not:

| Link was at | Came back at | Reported as | Means |
| --- | --- | --- | --- |
| Above 9600 | 9600 | `power_cycle` | The amplifier restarted. Nothing to fix. |
| Above 9600 | The same rate | `link_fault` | The amplifier never lost power, so the cable, adapter or bridge dropped. Go and reseat it. |
| 9600 | 9600 | `unknown` | Indistinguishable at the default rate. |

**If you want this diagnosis, set the target link speed above 9600.** At the
default both failures leave the amplifier at 9600 and there is nothing to tell
them apart. Raising it costs nothing, since the rate is renegotiated
automatically on every recovery, and it lowers latency as well.

Other signals worth checking together with it. A power cycle brings the
amplifier back on its own in well under a minute, and zone volumes and sources
survive it unchanged. An outage that lasts minutes with nothing answering at any
rate, and then clears the moment somebody touches the cable, was never a power
event.

### Zone and entity oddities

*   **The master zone mirrors zone 1.** A unit's master entity (zone 10, 20 or
    30) has no readable state of its own; the amplifier answers a whole-unit
    query with one record per zone, not a summary. Its *writes* genuinely reach
    every zone, but the state it displays is the first zone's. Judge "did it
    work" from the individual zones.
*   **Keypad text entities look empty or stale.** Source names and the keypad
    welcome message cannot be read back over RS-232 at all. Those entities show
    the last value *this integration* sent, not what the keypad is displaying,
    so after a restart they start blank even though the keypad still shows your
    text.
*   **A keypad name was rejected or truncated.** The hardware takes exactly 8
    characters and only plain ASCII. Longer text is truncated; accented or
    non-Latin characters are rejected with an error rather than sent as
    mangled bytes.
*   **Keypad status shows `disconnected` everywhere.** That is the amplifier
    reporting no keypad on that zone. If every zone reads `disconnected`, keypad
    presses are not something polling needs to catch and you can raise the
    **Poll interval** considerably; the front panel still changes state out of
    band, so do not disable polling entirely.
*   **`Sound Mode` moves the Bass slider.** It is a convenience preset that sets
    the zone's Bass value, not a hardware DSP mode.

### Using the `remote` entity for raw commands

*   **The amplifier does not range-check values.** A raw command such as
    `<11VO99` is echoed back without complaint even though the volume range is
    0-38. The clamping that protects the normal entities does not apply to raw
    commands, by design, so check your values.
*   **A rejected command raises an error.** When the amplifier answers
    `Command Error.`, the integration raises rather than carrying on, and treats
    the link as needing a resync on the next poll. A malformed command is the
    usual cause.

### Still stuck

Download the integration's **Diagnostics** file from the device page. It reports
redacted entry data, connection state, current and target baud, active units,
poll timing, and failure/reconnect counters. Arbitrary raw serial content is not
included, so it is safe to attach to an issue.

Protocol-level detail, including which facts were verified against hardware and
which come from other implementations, is in
[`docs/protocol.md`](docs/protocol.md).

---

## 🧪 Testing

The test suite covers wire framing, validation/identity, baud switching,
gateway serialization and shutdown, config/reconfigure ownership, coordinator
recovery, expansion rediscovery, and failed-initial-refresh cleanup:

```
pip install \
  "homeassistant==2026.8.3" \
  "pymonoprice==0.6.1" \
  pytest pytest-asyncio pytest-homeassistant-custom-component ruff mypy
ruff check custom_components tests
mypy --ignore-missing-imports --follow-imports=skip --allow-untyped-decorators custom_components/monoprice_custom
pytest -v
```

These tests use fakes and do not qualify a physical amplifier, clone, adapter,
or RS-232 cable. Live qualification remains a separate release activity.
