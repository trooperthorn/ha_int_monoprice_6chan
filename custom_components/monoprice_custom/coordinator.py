from datetime import timedelta
import logging
import time

from serial import SerialException, SerialTimeoutException
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

TARGET_BAUD = 38400

def optimize_serial_baudrate(amp, target_baud: int = TARGET_BAUD) -> int:
    """Negotiate optimal baud rate with the Monoprice amplifier."""
    if not hasattr(amp, "_port") or not amp._port:
        return 9600

    ser = amp._port

    # --- Step 1: Test if amp is ALREADY at target_baud ---
    ser.baudrate = target_baud
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    try:
        ser.write(b"?11\r")
        ser.flush()
        time.sleep(0.05)
        response = ser.read(30)
        if b">" in response:
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("Monoprice amplifier communicating at %d baud", target_baud)
            return target_baud
    except Exception:
        pass

    # --- Step 2: Fall back to 9600 baud (Power-On Default) ---
    ser.baudrate = 9600
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    try:
        ser.write(b"\r\n?11\r")
        ser.flush()
        time.sleep(0.05)
        response = ser.read(30)
        if b">" not in response:
            _LOGGER.warning("Monoprice amplifier did not respond at 9600 baud.")
            return 9600
    except Exception as err:
        _LOGGER.warning("Error checking 9600 baud baseline: %s", err)
        return 9600

    _LOGGER.info("Connected at 9600 baud. Upgrading speed to %d baud...", target_baud)

    # --- Step 3: Send speed upgrade command ($<BAUD'CR') ---
    try:
        cmd = f"$<{target_baud}\r".encode("ascii")
        ser.write(cmd)
        ser.flush()
        time.sleep(0.1)

        # --- Step 4: Switch local serial port to target_baud ---
        ser.baudrate = target_baud
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        # --- Step 5: Verify high-speed communication ---
        ser.write(b"?11\r")
        ser.flush()
        time.sleep(0.05)
        response_high = ser.read(30)

        if b">" in response_high:
            _LOGGER.info("Successfully upgraded Monoprice serial link to %d baud!", target_baud)
            return target_baud
    except Exception as err:
        _LOGGER.warning("Failed during baud rate upgrade attempt: %s", err)

    # --- Step 6: Failsafe Revert ---
    _LOGGER.warning("Reverting local serial port and amplifier to 9600 baud.")
    try:
        ser.write(b"$<9600\r")
        ser.flush()
        time.sleep(0.1)
    except Exception:
        pass

    ser.baudrate = 9600
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    return 9600


class MonopriceCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Monoprice data asynchronously."""

    def __init__(self, hass, api):
        """Initialize."""
        self.api = api
        
        # NEW: State trackers for recovery and speed optimization
        self.active_units: list[int] = []
        self._baud_optimized: bool = False
        
        super().__init__(
            hass,
            _LOGGER,
            name="Monoprice 6-Zone",
            update_interval=timedelta(seconds=5),
        )

    async def _async_update_data(self):
        """Fetch data from the amp via executor job."""
        try:
            # --- NEW: 1. Ensure Baud Rate is Optimized ---
            if not self._baud_optimized:
                await self.hass.async_add_executor_job(
                    optimize_serial_baudrate, self.api, TARGET_BAUD
                )
                self._baud_optimized = True

            # --- NEW: 2. One-Time Active Unit Discovery ---
            if not self.active_units:
                active = [1]
                try:
                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug("Probing for expansion Unit 2 (Zone 21)...")
                    status_u2 = await self.hass.async_add_executor_job(self.api.zone_status, 21)
                    if status_u2:
                        active.append(2)
                        
                        if _LOGGER.isEnabledFor(logging.DEBUG):
                            _LOGGER.debug("Probing for expansion Unit 3 (Zone 31)...")
                        status_u3 = await self.hass.async_add_executor_job(self.api.zone_status, 31)
                        if status_u3:
                            active.append(3)
                except Exception:
                    pass
                self.active_units = active
                
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("Active units locked to: %s", self.active_units)

            # --- ORIGINAL: Wake-up ping ---
            try:
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("Sending wake-up ping to amplifier.")
                await self.hass.async_add_executor_job(self.api.serial.write, b"\r\n")
            except Exception as e:
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("Wake-up ping failed (expected if locked): %s", e)

            zones = {}
            
            # --- MODIFIED: Loop only over discovered active units ---
            for unit in self.active_units:
                for j in range(1, 7):
                    zone_id = (unit * 10) + j
                    
                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug("Requesting status for Zone %s", zone_id)
                        
                    try:
                        zone_status = await self.hass.async_add_executor_job(
                            self.api.zone_status, zone_id
                        )
                        
                        if zone_status:
                            if _LOGGER.isEnabledFor(logging.DEBUG):
                                _LOGGER.debug(
                                    "Zone %s Response: Power=%s, Volume=%s, Source=%s", 
                                    zone_id, zone_status.power, zone_status.volume, zone_status.source
                                )
                            zones[zone_id] = zone_status
                            
                    except Exception as loop_err:
                        if "Connection timed out" in str(loop_err):
                            if _LOGGER.isEnabledFor(logging.DEBUG):
                                _LOGGER.debug("Timeout requesting Zone %s (Unit %s may not exist)", zone_id, unit)
                            if unit > 1:
                                pass # Ignore timeouts for secondary units
                            else:
                                raise loop_err
                        else:
                            raise loop_err

                # --- NEW: Poll Master Zone for unit (10, 20, 30) ---
                try:
                    master_id = unit * 10
                    master_status = await self.hass.async_add_executor_job(
                        self.api.zone_status, master_id
                    )
                    if master_status:
                        zones[master_id] = master_status
                except Exception:
                    pass
                            
            return zones
            
        except (SerialException, SerialTimeoutException) as err:
            # --- NEW: Connection Recovery ---
            self._baud_optimized = False
            _LOGGER.warning(
                "Monoprice communication error (%s). Connection state reset; re-negotiating baud rate on next poll.",
                err,
            )
            raise UpdateFailed(f"Error communicating with API: {err}")
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")
