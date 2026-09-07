9/6/26 - Config flow: the USB / Serial step now matches the Davis Vantage and Elk-M1 walkthrough (same step title, port label, and description). A failed verification re-shows the port selector with the error instead of a blank confirm form, for setup and reconfigure alike.

8/20/26 - Serial rework: fixed dead Text platform (never loaded), malformed baud-rate command, bass/treble number range mismatch, and unlocked raw serial writes racing the poll loop. Added PA/DND/rename/baud commands to a proper `api.py` client (switch.py's PA/DND controls previously called methods that didn't exist on the upstream library and would have crashed). Added via_device hierarchy, diagnostic entity category for the keypad sensor, reconfigure flow, configurable target baud rate, a `set_baud_rate` action, and per-zone targeted refresh after writes for lower latency.

4/24/22 - Fix balance controls on number entitys and monoprice_custom.set_balance
4/24/22 - Fix balance range monoprice_custom.set_balance from 1-19 to 0-20
4/24/22 - Disable zones 10, 20, 30 by default, there seems to be some issues with these zones. Enable with caution.