"""DataUpdateCoordinator for WaterLevel.ie."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    API_TIMEOUT,
    API_URL,
    DATA_RETENTION_HOURS,
    DEFAULT_UPDATE_INTERVAL,
    MAX_RETRY_ATTEMPTS,
    RETRY_BACKOFF_FACTOR,
)

_LOGGER = logging.getLogger(__name__)


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

        for feature in geojson.get("features", []):
            props = feature.get("properties", {})
            coords = feature.get("geometry", {}).get("coordinates", [None, None])
            station_id = props.get("station_ref")
            sensor_type = props.get("sensor_ref")
            value = props.get("value")
            timestamp = props.get("datetime")

            if not station_id or not sensor_type:
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

        return stations
