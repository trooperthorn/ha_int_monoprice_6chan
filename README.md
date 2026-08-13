# Home Assistant Custom Integration: Monoprice 6-Zone Amplifier

[![GitHub Release](https://img.shields.io/github/v/release/trooperthorn/ha_int_elkm1?style=for-the-badge)](https://github.com/trooperthorn/ha_int_monoprice_6chan/releases)
[![GitHub Activity](https://img.shields.io/github/commit-activity/m/trooperthorn/ha_int_elkm1?style=for-the-badge)](https://github.com/trooperthorn/ha_int_monoprice_6chan/commits/master)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)



A high-performance, completely rewritten Custom Integration for the Monoprice 6-Zone Amplifier (and compatible clones). This expands massively on the core Home Assistant integration by introducing high-speed serial communication, dynamic hardware discovery, and complete control over EQ, Public Address (PA), and Do Not Disturb (DND) modes.

![Control UI Screenshots](https://github.com/trooperthorn/ha_int_monoprice_6chan/blob/main/Screenshots/control-ui.png?raw=true)

---

## ✨ Key Features & Upgrades

This integration has been rebuilt around a modern, non-blocking `DataUpdateCoordinator` architecture to provide lightning-fast, highly reliable control:

*   🚀 **High-Speed Serial Auto-Negotiation:** The integration automatically detects the amplifier's current baud rate and upgrades it from the default 9600 baud to **38,400 baud**. This cuts command latency down to milliseconds for ultra-snappy UI responses.
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
*   **Balance:** Left/Right speaker balance (0 - 20)
*   **Bass:** Low-frequency EQ (-7 to +14)
*   **Treble:** High-frequency EQ (-7 to +14)

### Sensors
*   **Keypad Status:** Read-only diagnostic showing if the physical wall keypad for the zone is `Connected` or `Disconnected`.

---

## ⚙️ Installation

### Option 1: HACS (Recommended)
1. Open **HACS** -> **Integrations** -> **3 Dots (Top Right)** -> **Custom repositories**
2. Add this repository URL: `https://github.com/trooperthorn/ha_int_monoprice_6chan` (Category: Integration)
3. Click on the newly added **Monoprice 6-Zone Home Audio Controller** and click **Download**.
4. Restart Home Assistant.
5. Go to **Settings** -> **Devices & Services** -> **Add Integration** and search for **Monoprice 6-Zone Amplifier Custom**.

### Option 2: Manual
1. Copy the `monoprice` folder from this repository into your `/config/custom_components` directory.
2. Restart Home Assistant.
3. Go to **Settings** -> **Devices & Services** -> **Add Integration** and search for **Monoprice 6-Zone Amplifier Custom**.

> **Important Note:** If you are currently using the built-in "Core" Monoprice integration, you **must delete it** from your integrations list before configuring this custom version to prevent them from fighting over the serial port.

---

## 🔌 Configuration Best Practices

When configuring the integration, you will be asked to select your Serial Port. 

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
