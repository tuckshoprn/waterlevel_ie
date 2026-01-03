"""DataUpdateCoordinator for WaterLevel.ie."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    API_TIMEOUT,
    API_URL,
    DATA_RETENTION_HOURS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_RETRY_ATTEMPTS,
    RETRY_BACKOFF_FACTOR,
    STATION_REF_MAX,
    STATION_REF_MIN,
)

_LOGGER = logging.getLogger(__name__)

# Storage version for cached data
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.cache"


class WaterLevelDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching WaterLevel.ie data."""

    def __init__(
        self,
        hass: HomeAssistant,
        update_interval_minutes: int = DEFAULT_UPDATE_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="WaterLevel.ie Data",
            update_interval=timedelta(minutes=update_interval_minutes),
        )
        self._last_successful_update: datetime | None = None
        self._last_good_data: dict[str, Any] | None = None
        self._consecutive_failures = 0
        self._api_available = True

        # Storage for persisting cached data across restarts
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

    async def async_load_cache(self) -> None:
        """Load cached data from storage."""
        try:
            cached = await self._store.async_load()
            if cached and isinstance(cached, dict):
                # Check if we have valid cached data
                if "data" in cached and "timestamp" in cached:
                    timestamp_str = cached["timestamp"]
                    cached_time = dt_util.parse_datetime(timestamp_str)

                    if cached_time:
                        age = dt_util.utcnow() - cached_time
                        if age < timedelta(hours=DATA_RETENTION_HOURS):
                            self._last_good_data = cached["data"]
                            self._last_successful_update = cached_time
                            _LOGGER.info(
                                "Loaded cached data from %s ago (stored at %s)",
                                age,
                                timestamp_str,
                            )
                        else:
                            _LOGGER.debug(
                                "Cached data too old (%s), discarding",
                                age,
                            )
        except Exception as err:
            _LOGGER.warning("Failed to load cached data: %s", err)

    async def async_save_cache(self) -> None:
        """Save current data to storage."""
        if self._last_good_data and self._last_successful_update:
            try:
                await self._store.async_save(
                    {
                        "data": self._last_good_data,
                        "timestamp": self._last_successful_update.isoformat(),
                    }
                )
                _LOGGER.debug("Cached data saved to storage")
            except Exception as err:
                _LOGGER.warning("Failed to save cache: %s", err)

    @property
    def api_available(self) -> bool:
        """Return whether the API is currently available."""
        return self._api_available

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from WaterLevel.ie with retry logic and data retention."""
        session = async_get_clientsession(self.hass)
        last_exception = None

        # Try with exponential backoff
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                async with session.get(
                    API_URL,
                    timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
                ) as response:
                    response.raise_for_status()
                    geojson = await response.json()

                    # Success! Parse and store the data
                    parsed_data = self._parse_data(geojson)
                    self._last_good_data = parsed_data
                    self._last_successful_update = dt_util.utcnow()
                    self._consecutive_failures = 0

                    # Update API availability status
                    if not self._api_available:
                        _LOGGER.info("WaterLevel.ie API is back online")
                        self._api_available = True

                    # Save to persistent storage for future restarts
                    await self.async_save_cache()

                    return parsed_data

            except aiohttp.ClientResponseError as err:
                last_exception = err
                if err.status >= 500:
                    # Server error - worth retrying with backoff
                    if attempt < MAX_RETRY_ATTEMPTS - 1:
                        backoff = RETRY_BACKOFF_FACTOR**attempt
                        _LOGGER.debug(
                            "Server error (attempt %d/%d), retrying in %ds: %s",
                            attempt + 1,
                            MAX_RETRY_ATTEMPTS,
                            backoff,
                            err,
                        )
                        await asyncio.sleep(backoff)
                        continue
                else:
                    # Client error (4xx) - don't retry
                    break

            except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError) as err:
                last_exception = err
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    backoff = RETRY_BACKOFF_FACTOR**attempt
                    _LOGGER.debug(
                        "Connection error (attempt %d/%d), retrying in %ds: %s",
                        attempt + 1,
                        MAX_RETRY_ATTEMPTS,
                        backoff,
                        err,
                    )
                    await asyncio.sleep(backoff)
                else:
                    break

        # All retries failed
        self._consecutive_failures += 1
        self._api_available = False

        # Check if we have recent good data to return
        if self._last_good_data and self._last_successful_update:
            age = dt_util.utcnow() - self._last_successful_update
            if age < timedelta(hours=DATA_RETENTION_HOURS):
                # Log warning but only every 4 failures to reduce spam
                if self._consecutive_failures % 4 == 1:
                    _LOGGER.warning(
                        "WaterLevel.ie API unavailable (%d consecutive failures), "
                        "using cached data from %s ago. Last error: %s",
                        self._consecutive_failures,
                        age,
                        last_exception,
                    )
                return self._last_good_data

        # No valid cached data available
        error_msg = f"Error fetching data from {API_URL}"
        if last_exception:
            error_msg += f": {last_exception}"

        _LOGGER.error(
            "%s (failed %d times, no valid cached data available)",
            error_msg,
            self._consecutive_failures,
        )
        raise UpdateFailed(error_msg) from last_exception

    def _parse_data(self, geojson: dict[str, Any]) -> dict[str, Any]:
        """Parse GeoJSON data into station dictionary."""
        stations: dict[str, Any] = {}
        filtered_stations = set()

        for feature in geojson.get("features", []):
            props = feature.get("properties", {})
            coords = feature.get("geometry", {}).get("coordinates", [None, None])
            station_id = props.get("station_ref")
            station_name = props.get("station_name", "Unknown")
            sensor_type = props.get("sensor_ref")
            value = props.get("value")
            timestamp = props.get("datetime")

            if not station_id or not sensor_type:
                continue

            # Filter stations based on OPW restrictions
            # Only stations 00001-41000 are permitted for republication
            try:
                station_num = int(station_id)
                if not (STATION_REF_MIN <= station_num <= STATION_REF_MAX):
                    filtered_stations.add((station_id, station_num, station_name))
                    continue
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid station_ref format: %s", station_id)
                continue

            if station_id not in stations:
                stations[station_id] = {
                    "name": props.get("station_name", station_id),
                    "region": props.get("region_id"),
                    "location": f"{coords[1]}, {coords[0]}",
                    "last_updated": timestamp,
                    "sensors": {},
                }

            stations[station_id]["sensors"][sensor_type] = {
                "value": float(value) if value is not None else None,
                "datetime": timestamp,
            }

            # Update last_updated to the latest timestamp
            if timestamp and stations[station_id]["last_updated"]:
                if timestamp > stations[station_id]["last_updated"]:
                    stations[station_id]["last_updated"] = timestamp
            elif timestamp:
                stations[station_id]["last_updated"] = timestamp

        # Log filtered stations for transparency (OPW compliance)
        if filtered_stations:
            filtered_list = sorted(filtered_stations, key=lambda x: x[1])
            _LOGGER.info(
                "Filtered %d stations outside permitted range (%d-%d): %s",
                len(filtered_stations),
                STATION_REF_MIN,
                STATION_REF_MAX,
                ", ".join(f"{num} ({name})" for _, num, name in filtered_list),
            )

        return stations
