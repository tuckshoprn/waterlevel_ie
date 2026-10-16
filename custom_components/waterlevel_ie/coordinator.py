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
    FLOW_STATS_MAX_PER_UPDATE,
    FLOW_STATS_REFRESH_HOURS,
    FLOW_STATS_RETRY_HOURS,
    MAX_RETRY_ATTEMPTS,
    RETRY_BACKOFF_FACTOR,
    STATION_REF_MAX,
    STATION_REF_MIN,
)
from . import hydro

import re

def _normalise_name(name: str) -> str:
    """Lower-case and collapse whitespace for fuzzy station name matching."""
    return re.sub(r"\s+", " ", name.strip().lower())

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
        station_filter: set[str] | None = None,
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
        self._last_saved_data: dict[str, Any] | None = None
        self._consecutive_failures = 0
        self._api_available = True
        # Stations to track. Entries may be station refs (preferred) or names;
        # an empty filter means track all stations. We keep both the raw entries
        # (for exact ref matching) and normalised forms (for fuzzy name matching).
        self._station_filter: set[str] = set(station_filter) if station_filter else set()
        self._station_filter_normalised: set[str] = {
            _normalise_name(s) for s in self._station_filter
        }
        if self._station_filter:
            _LOGGER.debug("WaterLevel.ie: tracking %d station(s): %s", len(self._station_filter), self._station_filter)

        # Index of all OPW-permitted stations seen in the feed (ref -> name),
        # regardless of the active filter. Used to populate the options picker.
        self.available_stations: dict[str, str] = {}

        # River system name -> device registry id, filled in at setup so
        # station devices can link to their river via via_device_id.
        self.river_device_ids: dict[str, str] = {}

        # Latest OPW Hydro-Data discharge per station number, and per-station
        # flow statistics ({"fetched": datetime, "stats": dict}).
        self._flow_latest: dict[str, dict[str, Any]] = {}
        self._flow_stats: dict[str, dict[str, Any]] = {}

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
            # Skip the write if the data is unchanged since the last save to
            # avoid needless disk I/O every update cycle.
            if self._last_good_data == self._last_saved_data:
                _LOGGER.debug("Cached data unchanged, skipping save")
                return
            try:
                await self._store.async_save(
                    {
                        "data": self._last_good_data,
                        "timestamp": self._last_successful_update.isoformat(),
                    }
                )
                self._last_saved_data = self._last_good_data
                _LOGGER.debug("Cached data saved to storage")
            except Exception as err:
                _LOGGER.warning("Failed to save cache: %s", err)

    async def async_available_stations(self) -> dict[str, str]:
        """Return {station_ref: name} of permitted stations for the picker.

        Uses the index built during normal updates; if it is empty (e.g. the
        integration is currently running on cached data), fetch the feed once
        to populate it. Never raises - returns an empty dict on failure.
        """
        if self.available_stations:
            return self.available_stations
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                API_URL, timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
            ) as response:
                response.raise_for_status()
                geojson = await response.json()
            # Side effect: _parse_data populates self.available_stations.
            self._parse_data(geojson)
        except Exception as err:  # noqa: BLE001 - best effort for the picker
            _LOGGER.warning("Could not fetch station list for options flow: %s", err)
        return self.available_stations

    @property
    def api_available(self) -> bool:
        """Return whether the API is currently available."""
        return self._api_available

    @property
    def last_successful_update(self) -> datetime | None:
        """Return the timestamp of the last successful update."""
        return self._last_successful_update

    @property
    def consecutive_failures(self) -> int:
        """Return the number of consecutive update failures."""
        return self._consecutive_failures

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
                    await self._async_add_flow(session, parsed_data)
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

    async def _async_add_flow(
        self, session: aiohttp.ClientSession, stations: dict[str, Any]
    ) -> None:
        """Merge OPW Hydro-Data discharge and flow percentiles into stations.

        Best effort: a Hydro-Data failure never fails the main update; the last
        good flow values are reused instead. Only gauges with a rating curve
        publish flow, so other stations simply get no flow sensors.
        """
        try:
            async with session.get(
                hydro.FLOW_LAYER_URL,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
            ) as response:
                response.raise_for_status()
                layer = hydro.parse_layer(await response.json(content_type=None))
            if layer:
                self._flow_latest = layer
        except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError, ValueError) as err:
            _LOGGER.debug("Hydro-Data flow layer unavailable, reusing last values: %s", err)

        now = dt_util.utcnow()
        budget = FLOW_STATS_MAX_PER_UPDATE
        for station_id, station in stations.items():
            number = hydro.station_no(station_id)
            flow = self._flow_latest.get(number) if number else None
            if flow is None:
                continue
            flow_sensor: dict[str, Any] = {
                "value": flow["value"],
                "datetime": flow["datetime"],
            }
            station["sensors"][hydro.FLOW] = flow_sensor

            cached = self._flow_stats.get(number)
            if budget and (
                cached is None
                or now - cached["fetched"] > timedelta(hours=FLOW_STATS_REFRESH_HOURS)
            ):
                budget -= 1
                stats = await self._async_fetch_flow_stats(session, number)
                if stats is not None:
                    cached = {"fetched": now, "stats": stats}
                elif cached is None:
                    # Retry a failed first fetch after an hour, not a day.
                    cached = {
                        "fetched": now
                        - timedelta(hours=FLOW_STATS_REFRESH_HOURS - FLOW_STATS_RETRY_HOURS),
                        "stats": {},
                    }
                self._flow_stats[number] = cached

            stats = cached["stats"] if cached else {}
            if not stats:
                continue
            flow_sensor["attributes"] = {
                key: stats[key]
                for key in ("long_term_average", "median_annual_max", "highest_annual_max")
                if key in stats
            }
            percentile = hydro.flow_percentile(flow["value"], stats.get("percentiles"))
            if percentile is not None:
                station["sensors"][hydro.FLOW_PERCENTILE] = {
                    "value": percentile,
                    "datetime": flow["datetime"],
                    "attributes": {
                        "exceedance_flows_m3s": {
                            f"Q{p:02d}": q for p, q in stats["percentiles"].items()
                        },
                    },
                }

    async def _async_fetch_flow_stats(
        self, session: aiohttp.ClientSession, number: str
    ) -> dict[str, Any] | None:
        """Fetch one station's flow statistics; None on failure."""
        try:
            async with session.get(
                hydro.flow_stats_url(number),
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
            ) as response:
                response.raise_for_status()
                return hydro.parse_flow_stats(await response.json(content_type=None))
        except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError, ValueError) as err:
            _LOGGER.debug("Hydro-Data flow statistics unavailable for %s: %s", number, err)
            return None

    def _parse_data(self, geojson: dict[str, Any]) -> dict[str, Any]:
        """Parse GeoJSON data into station dictionary."""
        stations: dict[str, Any] = {}
        filtered_stations = set()
        available: dict[str, str] = {}

        for feature in geojson.get("features", []):
            props = feature.get("properties", {})
            geometry = feature.get("geometry") or {}
            coords = geometry.get("coordinates") or []
            longitude = coords[0] if len(coords) > 0 else None
            latitude = coords[1] if len(coords) > 1 else None
            station_id = props.get("station_ref")
            station_name = props.get("station_name", "Unknown")
            sensor_type = props.get("sensor_ref")
            value = props.get("value")
            timestamp = props.get("datetime")

            if not station_id or not sensor_type:
                continue

            # Enforce OPW republication restrictions first - only stations
            # 00001-41000 are permitted for republication.
            try:
                station_num = int(station_id)
                if not (STATION_REF_MIN <= station_num <= STATION_REF_MAX):
                    filtered_stations.add((station_id, station_num, station_name))
                    continue
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid station_ref format: %s", station_id)
                continue

            # Record every permitted station for the options picker, regardless
            # of the active tracking filter.
            available[station_id] = station_name

            # Apply the user-configured tracking filter (if any). Match on the
            # station ref (preferred) or, for backwards compatibility, the name.
            if self._station_filter and (
                station_id not in self._station_filter
                and _normalise_name(station_name) not in self._station_filter_normalised
            ):
                continue

            if station_id not in stations:
                stations[station_id] = {
                    "name": props.get("station_name", station_id),
                    "region": props.get("region_id"),
                    "location": f"{latitude}, {longitude}",
                    "last_updated": timestamp,
                    "sensors": {},
                }

            try:
                parsed_value = float(value) if value is not None else None
            except (ValueError, TypeError):
                _LOGGER.warning(
                    "Invalid value %r for station %s sensor %s, skipping",
                    value,
                    station_id,
                    sensor_type,
                )
                continue

            stations[station_id]["sensors"][sensor_type] = {
                "value": parsed_value,
                "datetime": timestamp,
            }

            # Update last_updated to the latest timestamp. Compare parsed
            # datetimes rather than raw strings so differing formats/offsets
            # still order correctly; the original string is kept for display.
            if timestamp:
                current = stations[station_id]["last_updated"]
                new_dt = dt_util.parse_datetime(timestamp)
                current_dt = dt_util.parse_datetime(current) if current else None
                if current_dt is None or (new_dt is not None and new_dt > current_dt):
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

        # Refresh the picker index with every permitted station seen this cycle.
        if available:
            self.available_stations = available

        return stations
