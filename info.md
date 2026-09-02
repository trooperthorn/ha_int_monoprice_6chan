 An Integration for the Monoprice 6-Zone Amplifier, with added sound mode, balance, treble & bass
 This is a modification of the <a href="https://www.home-assistant.io/integrations/monoprice/">existing Monoprice integration</a>.
 
 <b>Note:</b> if you your zones are slow to respond, make sure all entities in the zones you are not using are disabled in Home Assistant.

 ![alt text](https://github.com/thebradleysanders/Monoprice-6-Zone-Home-Controller/blob/main/Screenshots/control-ui.png?raw=true)

## How To:
### <a href="https://github.com/hacs/integration">HACS</a>
* Open HACS->Integrations->3 Dots->Custom repositories
* Add this repository url: https://github.com/trooperthorn/ha_int_monoprice_6chan
* Click on the newly added Monoprice 6-Zone Home Audio Controller
* Click Download this repository with HACS
* Restart Home Assistant
* Go to Settings->Integrations->Add->Monoprice 6-Zone Amplifier Custom
* Select the serial interface, verify the amplifier, then configure source names and target baud

### Manual
* Add the monoprice_custom folder to your /config/custom_components folder
* Restart Home Assistant
* Go to Settings->Integrations->Add->Monoprice 6-Zone Amplifier Custom
* Select the serial interface, verify the amplifier, then configure source names and target baud

<b>Legacy-domain migration:</b> Releases through 2026.08.20 used the same
<code>monoprice</code> domain as Home Assistant Core. Disable the existing
entry, restart Home Assistant, and add this integration as
<code>monoprice_custom</code>. Remove the legacy entry only after the new entry
has been verified. Never enable both entries against the same serial port.


## Additional Features
These are features not included in the original Monoprice Integration.

 #### Zones
 * 10 - Used to control all zones on the master controller <b>- Entity Disabled, there are known issues, alpha feature.</b>
 * 20 - Used to control all zones on the slave 1 controller <b>- Entity Disabled, there are known issues, alpha feature.</b>
 * 30 - Used to control all zones on the slave 2 controller <b>- Entity Disabled, there are known issues, alpha feature.</b>

 #### Services
 * <i>monoprice_custom.snapshot</i> 
 * <i>monoprice_custom.restore</i>
 * monoprice_custom.set_balance
 * monoprice_custom.set_bass
 * monoprice_custom.set_treble

 #### Sound Modes
 The sound modes can be controlled via a select dropdown on the media_player card.
 The sound modes are:
 * Normal
 * High Bass
 * Medium Bass
 * Low Bass

  #### Sensors
  * Keypad (Connected/Disconnected)
  * Do Not Disturb (On/Off)
  * Public Anouncement (On/Off)
  
  #### Sliders (Numbers)
  * Balance
  * Bass
  * Treble
