"""River lookup for WaterLevel.ie stations.

Maps station references to the river they sit on, using a static map generated
offline from the EPA river network (1:50,000). Used to group/filter stations by
river system in the options flow. Stations not in the map (coastal, tidal or
lake gauges) simply have no river.
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache

_LOGGER = logging.getLogger(__name__)

_DATA_FILE = os.path.join(os.path.dirname(__file__), "station_rivers.json")


@lru_cache(maxsize=1)
def _river_map() -> dict[str, str]:
    """Load and cache the station_ref -> river name map."""
    try:
        with open(_DATA_FILE, encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError) as err:
        _LOGGER.warning("Could not load river map: %s", err)
    return {}


def station_river_map() -> dict[str, str]:
    """Return a copy of the full station_ref -> river name map."""
    return dict(_river_map())


def river_for_ref(ref: str) -> str | None:
    """Return the river name for a station ref, or None if unknown."""
    return _river_map().get(ref)


def rivers_for_refs(refs: set[str] | None = None) -> list[str]:
    """Return the sorted distinct rivers, optionally limited to the given refs."""
    river_map = _river_map()
    if refs is None:
        rivers = set(river_map.values())
    else:
        rivers = {river_map[r] for r in refs if r in river_map}
    return sorted(rivers, key=str.lower)


def refs_for_rivers(rivers: set[str] | list[str]) -> set[str]:
    """Return all station refs that belong to any of the given rivers."""
    wanted = set(rivers)
    return {ref for ref, river in _river_map().items() if river in wanted}
