"""Binary sensor platform for WaterLevel.ie integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WaterLevelDataCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WaterLevel.ie binary sensors."""
    coordinator: WaterLevelDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([WaterLevelAPIStatusSensor(coordinator)])


class WaterLevelAPIStatusSensor(
    CoordinatorEntity[WaterLevelDataCoordinator], BinarySensorEntity
):
    """Binary sensor representing WaterLevel.ie API availability."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    # Note: Not marked as diagnostic so it's visible in UI for monitoring

    def __init__(self, coordinator: WaterLevelDataCoordinator) -> None:
        """Initialize the API status sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_api_status"
        self._attr_name = "API Status"

    @property
    def is_on(self) -> bool:
        """Return True if the API is available."""
        return self.coordinator.api_available

    @property
    def available(self) -> bool:
        """Always return True - we want to show API status even during outages."""
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes about API status."""
        attrs = {
            "api_url": "https://waterlevel.ie/geojson/latest/",
        }

        if self.coordinator._last_successful_update:
            attrs["last_successful_update"] = (
                self.coordinator._last_successful_update.isoformat()
            )

        if self.coordinator._consecutive_failures > 0:
            attrs["consecutive_failures"] = self.coordinator._consecutive_failures

        return attrs

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for the WaterLevel.ie service."""
        return {
            "identifiers": {(DOMAIN, "waterlevel_ie_service")},
            "name": "! WaterLevel.ie API",
            "manufacturer": "OPW Ireland",
            "model": "API Service",
            "configuration_url": "https://waterlevel.ie/",
        }
