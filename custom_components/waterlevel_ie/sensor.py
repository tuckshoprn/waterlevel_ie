from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import UnitOfTemperature, UnitOfLength
from homeassistant.units import UnitOfFlowRate

from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

SENSOR_NAMES = {
    "0001": "Water Level",
    "0002": "Water Temperature",
    "0003": "Flow Rate",
    "OD": "Ordnance Datum",
}

SENSOR_UNITS = {
    "0001": UnitOfLength.CENTIMETERS,
    "0002": UnitOfTemperature.CELSIUS,
    "0003": UnitOfFlowRate.CUBIC_METERS_PER_SECOND,
    "OD": UnitOfLength.METERS,
}

SENSOR_DEVICE_CLASSES = {
    "0001": "water",
    "0002": "temperature",
    "0003": "volume_flow_rate",
    "OD": "distance",
}

SENSOR_ICONS = {
    "0001": "mdi:waves",
    "0002": "mdi:thermometer-water",
    "0003": "mdi:pipe",
    "OD": "mdi:altimeter",
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for station_id, station in coordinator.data.items():
        for sensor_type in station["sensors"]:
            entities.append(WaterLevelSensor(coordinator, station_id, station, sensor_type))

    async_add_entities(entities)


class WaterLevelSensor(CoordinatorEntity, Entity):
    def __init__(self, coordinator, station_id, station, sensor_type):
        super().__init__(coordinator)
        self._station_id = station_id
        self._station = station
        self._sensor_type = sensor_type

    @property
    def name(self):
        sensor_name = SENSOR_NAMES.get(self._sensor_type, self._sensor_type)
        return f"{self._station['name']} {sensor_name}"

    @property
    def unique_id(self):
        return f"{self._station_id}_{self._sensor_type}"

    @property
    def state(self):
        return self._station["sensors"].get(self._sensor_type, {}).get("value")

    @property
    def native_unit_of_measurement(self):
        return SENSOR_UNITS.get(self._sensor_type)

    @property
    def device_class(self):
        return SENSOR_DEVICE_CLASSES.get(self._sensor_type)

    @property
    def icon(self):
        return SENSOR_ICONS.get(self._sensor_type, "mdi:water")

    @property
    def extra_state_attributes(self):
        sensor_info = self._station["sensors"].get(self._sensor_type, {})
        lat, lon = map(float, self._station.get("location", "0,0").split(", "))
        return {
            "region": self._station.get("region"),
            "last_updated": sensor_info.get("datetime"),
            "latitude": lat,
            "longitude": lon,
            "location_link": f"https://www.google.com/maps/search/?api=1&query={lat},{lon}",
            "attribution": "Data provided by WaterLevel.ie (OPW)"
        }

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._station_id)},
            "name": self._station["name"],
            "manufacturer": "WaterLevel.ie",
            "model": "Hydrometric Station",
            "entry_type": "service",
            "configuration_url": "https://waterlevel.ie/"
        }