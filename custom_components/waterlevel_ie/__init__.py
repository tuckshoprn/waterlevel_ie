"""WaterLevel.ie integration for Home Assistant."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_RIVERS,
    CONF_STATIONS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_RIVERS,
    DEFAULT_STATIONS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .coordinator import WaterLevelDataCoordinator
from . import rivers as rivers_mod

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up WaterLevel.ie from a config entry."""
    update_interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    stations_raw = entry.options.get(CONF_STATIONS, DEFAULT_STATIONS)
    # The picker stores a list of station refs; older configs stored a newline
    # separated string of station names. Accept either form.
    if isinstance(stations_raw, list):
        station_filter = {str(s).strip() for s in stations_raw if str(s).strip()}
    elif isinstance(stations_raw, str):
        station_filter = {s.strip() for s in stations_raw.splitlines() if s.strip()}
    else:
        station_filter = set()

    # Expand any selected river systems into their station refs and add them to
    # the explicit station selection. Empty selection = track all stations.
    selected_rivers = entry.options.get(CONF_RIVERS, DEFAULT_RIVERS) or []
    if selected_rivers:
        river_refs = await hass.async_add_executor_job(
            rivers_mod.refs_for_rivers, selected_rivers
        )
        station_filter |= river_refs

    coordinator = WaterLevelDataCoordinator(hass, update_interval, station_filter)

    # Load any cached data from previous runs before first refresh
    await coordinator.async_load_cache()

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
