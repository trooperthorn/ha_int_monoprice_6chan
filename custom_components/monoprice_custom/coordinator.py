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
            # Wrap synchronous status polling
            zones = {}
            for zone_id in range(11, 17): # Zones 1-6
                zone_status = await self.hass.async_add_executor_job(
                    self.api.zone_status, zone_id
                )
                if zone_status:
                    zones[zone_id] = zone_status
            return zones
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")
