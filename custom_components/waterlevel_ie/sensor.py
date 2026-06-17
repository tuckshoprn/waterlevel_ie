"""Sensor platform for WaterLevel.ie integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import WaterLevelDataCoordinator
from . import rivers as rivers_mod

_LOGGER = logging.getLogger(__name__)

# Sensor metadata with display precision for better long-term statistics
SENSOR_NAMES: dict[str, str] = {
    "0001": "Water Level",
    "0002": "Water Temperature",
    "0003": "Flow Rate",
    "OD": "Ordnance Datum",
}

SENSOR_UNITS: dict[str, str] = {
    "0001": "m",
    "0002": "°C",
    "0003": "m³/s",
}

SENSOR_DEVICE_CLASSES: dict[str, SensorDeviceClass] = {
    "0001": SensorDeviceClass.DISTANCE,
    "0002": SensorDeviceClass.TEMPERATURE,
    "0003": SensorDeviceClass.VOLUME_FLOW_RATE,
    # "OD" will be plain number, no device_class
}

SENSOR_ICONS: dict[str, str] = {
    "0001": "mdi:waves",
    "0002": "mdi:thermometer-water",
    "0003": "mdi:pipe",
    "OD": "mdi:altimeter",
}

# Suggested display precision for each sensor type
SENSOR_PRECISION: dict[str, int] = {
    "0001": 3,  # Water level to mm precision
    "0002": 1,  # Temperature to 0.1°C
    "0003": 3,  # Flow rate to 3 decimal places
    "OD": 2,  # Ordnance datum to cm precision
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WaterLevel.ie sensors."""
    coordinator: WaterLevelDataCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[tuple[str, str]] = set()

    @callback
    def _add_new_entities() -> None:
        """Add entities for any stations/sensors not seen before."""
        new_entities: list[WaterLevelSensor] = []
        for station_id, station in coordinator.data.items():
            for sensor_type in station["sensors"]:
                key = (station_id, sensor_type)
                if key not in known:
                    known.add(key)
                    new_entities.append(
                        WaterLevelSensor(coordinator, station_id, sensor_type)
                    )
        if new_entities:
            async_add_entities(new_entities)

    # Initial population, then add any new stations that appear in later updates
    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class WaterLevelSensor(CoordinatorEntity[WaterLevelDataCoordinator], SensorEntity):
    """Representation of a WaterLevel.ie sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WaterLevelDataCoordinator,
        station_id: str,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._station_id = station_id
        self._sensor_type = sensor_type

        # Precompute names and location
        station = coordinator.data.get(station_id, {})
        self._station_name = station.get("name", station_id)
        self._sensor_name = SENSOR_NAMES.get(sensor_type, sensor_type)

        # Parse coordinates safely
        try:
            location = station.get("location", "0,0")
            lat_str, lon_str = location.split(", ")
            self._lat = float(lat_str)
            self._lon = float(lon_str)
        except (ValueError, AttributeError):
            _LOGGER.warning("Invalid location format for station %s", station_id)
            self._lat = 0.0
            self._lon = 0.0

    @property
    def name(self) -> str:
        """Friendly name for the sensor."""
        return f"{self._station_name} {self._sensor_name}"

    @property
    def unique_id(self) -> str:
        """Unique ID for entity registry. Preserves history."""
        return f"{self._station_id}_{self._sensor_type}"

    @property
    def native_value(self) -> float | None:
        """Return the sensor's current value."""
        station = self.coordinator.data.get(self._station_id, {})
        value = station.get("sensors", {}).get(self._sensor_type, {}).get("value")
        return value

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Unit of measurement."""
        if self._sensor_type == "OD":
            return None
        return SENSOR_UNITS.get(self._sensor_type)

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return the device class, except OD is just a number."""
        if self._sensor_type == "OD":
            return None
        return SENSOR_DEVICE_CLASSES.get(self._sensor_type)

    @property
    def state_class(self) -> SensorStateClass:
        """Momentary measurement with long-term statistics."""
        return SensorStateClass.MEASUREMENT

    @property
    def suggested_display_precision(self) -> int | None:
        """Return the suggested display precision for long-term statistics."""
        return SENSOR_PRECISION.get(self._sensor_type)

    @property
    def icon(self) -> str:
        """Icon for the sensor."""
        return SENSOR_ICONS.get(self._sensor_type, "mdi:water")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Extra attributes like location and timestamp."""
        station = self.coordinator.data.get(self._station_id, {})
        sensor_info = station.get("sensors", {}).get(self._sensor_type, {})

        attrs = {
            "region": station.get("region"),
            "last_updated": sensor_info.get("datetime"),
            "latitude": self._lat,
            "longitude": self._lon,
            "location_link": f"https://www.google.com/maps/search/?api=1&query={self._lat},{self._lon}",
            "attribution": "Data provided by WaterLevel.ie (OPW)",
        }

        # Add information about cached data if API is unavailable
        if not self.coordinator.api_available and self.coordinator.last_successful_update:
            attrs["using_cached_data"] = True
            attrs["data_age_hours"] = round(
                (
                    dt_util.utcnow()
                    - self.coordinator.last_successful_update
                ).total_seconds()
                / 3600,
                1,
            )

        return attrs

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info to group all sensors of the same station.

        When the station's river is known, nest this device under its river
        system device via via_device so gauges group by river.
        """
        info: dict[str, Any] = {
            "identifiers": {(DOMAIN, self._station_id)},
            "name": self._station_name,
            "manufacturer": "WaterLevel.ie",
            "model": "Hydrometric Station",
            "configuration_url": "https://waterlevel.ie/",
        }
        river = rivers_mod.river_for_ref(self._station_id)
        if river:
            info["via_device"] = (DOMAIN, f"river:{river}")
        return info
