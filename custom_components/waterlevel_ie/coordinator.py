import logging
from datetime import timedelta
import aiohttp

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

URL = "https://waterlevel.ie/geojson/latest/"

class WaterLevelDataCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant):
        super().__init__(
            hass,
            _LOGGER,
            name="WaterLevel.ie Data",
            update_interval=timedelta(minutes=15),
        )

    async def _async_update_data(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(URL) as response:
                    geojson = await response.json()
                    return self._parse_data(geojson)
        except Exception as e:
            _LOGGER.error("Failed to fetch data: %s", e)
            return {}

    def _parse_data(self, geojson):
        stations = {}

        for feature in geojson.get("features", []):
            props = feature.get("properties", {})
            coords = feature.get("geometry", {}).get("coordinates", [None, None])
            station_id = props.get("station_ref")
            sensor_type = props.get("sensor_ref")
            value = props.get("value")
            timestamp = props.get("datetime")

            if station_id not in stations:
                stations[station_id] = {
                    "name": props.get("station_name"),
                    "region": props.get("region_id"),
                    "location": f"{coords[1]}, {coords[0]}",
                    "last_updated": timestamp,
                    "sensors": {}
                }

            stations[station_id]["sensors"][sensor_type] = {
                "value": float(value) if value is not None else None,
                "datetime": timestamp,
            }

            if timestamp > stations[station_id]["last_updated"]:
                stations[station_id]["last_updated"] = timestamp

        return stations