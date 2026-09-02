# Home Assistant Custom Integration: Monoprice 6-Zone Amplifier

[![GitHub Release](https://img.shields.io/github/v/release/trooperthorn/ha_int_monoprice_6chan?style=for-the-badge)](https://github.com/trooperthorn/ha_int_monoprice_6chan/releases)
[![GitHub Activity](https://img.shields.io/github/commit-activity/m/trooperthorn/ha_int_monoprice_6chan?style=for-the-badge)](https://github.com/trooperthorn/ha_int_monoprice_6chan/commits/master)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)



A high-performance, completely rewritten Custom Integration for the Monoprice 6-Zone Amplifier (and compatible clones). This expands massively on the core Home Assistant integration by introducing high-speed serial communication, dynamic hardware discovery, and complete control over EQ, Public Address (PA), and Do Not Disturb (DND) modes.

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

Configuration is deliberately staged: select a serial interface, explicitly
verify the amplifier on that interface, then choose source names and the target
baud rate. Merely rendering the selector does not open or probe any port.

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

The amplifier always powers on at 9600 baud. On first poll after startup the integration negotiates up to a faster **target link speed**, configurable from **Settings → Devices & Services → Monoprice → Configure** (defaults to 9600 unless changed). A higher rate lowers per-command latency but is more sensitive to long or noisy RS-232 runs — if you see intermittent timeouts after raising it, step back down one notch. The amp reverts to 9600 baud on every power cycle, so the integration re-negotiates automatically whenever a connection error is detected.

---

## 🔁 Reconfiguring

If you move the amplifier to a different USB/serial port, use **Settings → Devices & Services → Monoprice → Reconfigure** instead of removing and re-adding the integration — it keeps your existing entities, automations, and history intact.

---

## ⚠️ Known Limitations

*   The amplifier's Public Address input is a fixed hardware pin (not a `media_player.play_media` target); to page a zone, route your announcement device's audio into the amp's PA input and toggle the `Public Address` switch.
*   The `Sound Mode` dropdown on each zone media player is a convenience preset that just sets the zone's Bass value — it isn't a hardware DSP mode, and it will move the Bass number entity's slider when used.
*   Source names/keypad messages are limited to 8 ASCII characters by the hardware; longer input is silently truncated.

## 🩺 Troubleshooting

*   **"Cannot connect" during verification:** confirm that no other integration or process owns the selected interface. Only the submitted interface is opened, and the verifier closes it before setup continues.
*   **"Not a Monoprice amplifier" during verification:** the interface opened successfully but did not return a structurally valid Zone 11 response at a supported baud rate.
*   **Entities go `Unavailable` intermittently:** usually a baud-rate mismatch on a long/noisy cable run — lower the target link speed in **Configure**.
*   **An expansion unit is unavailable:** discovery retries after recovery and every five minutes. A newly detected unit is added dynamically; an existing unit that returns becomes available again without a restart.
*   For deeper diagnosis, download the integration's **Diagnostics** file from the device page. It reports redacted entry data, connection state, current/target baud, active units, poll timing, and failure/reconnect counters; arbitrary raw serial content is not included.

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
