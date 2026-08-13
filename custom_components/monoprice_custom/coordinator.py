from datetime import timedelta
import logging
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

class MonopriceCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Monoprice data asynchronously."""

    def __init__(self, hass, api):
        """Initialize."""
        self.api = api
        super().__init__(
            hass,
            _LOGGER,
            name="Monoprice 6-Zone",
            update_interval=timedelta(seconds=5),
        )

    async def _async_update_data(self):
        """Fetch data from the amp via executor job."""
        try:
            # Wake-up ping
            try:
                _LOGGER.debug("Sending wake-up ping to amplifier.")
                await self.hass.async_add_executor_job(self.api.serial.write, b"\r\n")
            except Exception as e:
                _LOGGER.debug("Wake-up ping failed (expected if locked): %s", e)

            zones = {}
            for i in range(1, 4):
                for j in range(1, 7):
                    zone_id = (i * 10) + j
                    
                    # Performance optimization: Only build log strings if debug is on
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
                                _LOGGER.debug("Timeout requesting Zone %s (Unit %s may not exist)", zone_id, i)
                            if i > 1:
                                pass # Ignore timeouts for secondary units
                            else:
                                raise loop_err
                        else:
                            raise loop_err
                            
            return zones
            
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")
