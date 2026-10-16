"""OPW Hydro-Data helpers: river discharge and flow statistics.

The waterlevel.ie live feed carries level, temperature and logger battery
voltage only. Discharge (flow) is published separately by OPW Hydro-Data
(https://waterlevel.ie/hydro-data/, CC BY 4.0), only for gauges with a rating
curve. Pure functions with no Home Assistant imports so they can be tested
standalone.
"""
from __future__ import annotations

import math
from typing import Any

HYDRO_BASE_URL = "https://waterlevel.ie/hydro-data/data/internet"
# Bulk "latest value" layer for discharge: one request covers every station.
FLOW_LAYER_URL = f"{HYDRO_BASE_URL}/layers/30/index.json"
HYDRO_ATTRIBUTION = (
    "Contains Irish Public Sector Information licensed under CC BY 4.0 "
    "(source https://waterlevel.ie/hydro-data/ - provided by the Office of Public Works)"
)
HYDRO_DISCLAIMER_URL = "https://waterlevel.ie/hydro-data/html/disclaimer.html"

# Sensor keys used in the coordinator's per-station "sensors" dict.
FLOW = "Q"
FLOW_PERCENTILE = "Q_PCT"


def station_no(station_ref: str) -> str | None:
    """Map a live-feed ref ("0000034001") to a Hydro-Data station number ("34001")."""
    try:
        return f"{int(station_ref):05d}"
    except (TypeError, ValueError):
        return None


def flow_stats_url(number: str) -> str:
    """URL of a station's flow statistics (percentiles, averages, annual maxima)."""
    return f"{HYDRO_BASE_URL}/stations/0/{number}/Q/alarmlevel.json"


def parse_layer(rows: Any) -> dict[str, dict[str, Any]]:
    """Parse a Hydro-Data layer into {station_no: {"value", "datetime"}}."""
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, dict):
            continue
        number = row.get("station_no")
        try:
            value = float(row["ts_value"])
        except (KeyError, TypeError, ValueError):
            continue
        if number and math.isfinite(value):
            result[str(number)] = {"value": value, "datetime": row.get("timestamp")}
    return result


def _last_value(series: dict[str, Any]) -> float | None:
    for point in reversed(series.get("data") or []):
        try:
            return float(point[1])
        except (IndexError, TypeError, ValueError):
            continue
    return None


def parse_flow_stats(series_list: Any) -> dict[str, Any]:
    """Parse alarmlevel.json into exceedance percentiles and summary flows.

    OPW percentiles are exceedance percentiles: Percentile-95 is the flow
    exceeded 95% of the time (a low flow), Percentile-01 a flood flow.
    """
    percentiles: dict[int, float] = {}
    stats: dict[str, Any] = {}
    if not isinstance(series_list, list):
        return {}
    for series in series_list:
        if not isinstance(series, dict):
            continue
        name = series.get("ts_name") or series.get("ts_shortname") or ""
        value = _last_value(series)
        if value is None:
            continue
        if name.startswith("WEB.Percentile-"):
            try:
                percentiles[int(name.rsplit("-", 1)[1])] = value
            except ValueError:
                continue
        elif name == "WEB.LongTermAverage":
            stats["long_term_average"] = value
        elif name == "WEB.YearHyd.Amax(median)":
            stats["median_annual_max"] = value
        elif name == "WEB.YearHyd.Amax(highest)":
            stats["highest_annual_max"] = value
    if len(percentiles) >= 2:
        stats["percentiles"] = dict(sorted(percentiles.items()))
    return stats


def flow_percentile(flow: float | None, percentiles: dict[int, float] | None) -> float | None:
    """Return where `flow` sits in the station's record, 0-100 (higher = more water).

    Interpolates the flow duration curve in log-flow space between OPW's
    exceedance percentiles, then reports the non-exceedance percentile, so 50
    is a median flow and 90 means only 10% of the record was higher. Clamped
    to the published range (e.g. 1-99).
    """
    if flow is None or not percentiles or len(percentiles) < 2:
        return None
    # Exceedance % ascending -> flow descending.
    points = sorted((int(p), float(q)) for p, q in percentiles.items())
    if flow >= points[0][1]:
        return round(100.0 - points[0][0], 1)
    if flow <= points[-1][1]:
        return round(100.0 - points[-1][0], 1)
    for (p_hi, q_hi), (p_lo, q_lo) in zip(points, points[1:]):
        if q_hi >= flow >= q_lo:
            if q_hi == q_lo:
                exceedance = float(p_hi)
            elif min(q_hi, q_lo, flow) > 0:
                t = (math.log(q_hi) - math.log(flow)) / (math.log(q_hi) - math.log(q_lo))
                exceedance = p_hi + t * (p_lo - p_hi)
            else:
                t = (q_hi - flow) / (q_hi - q_lo)
                exceedance = p_hi + t * (p_lo - p_hi)
            return round(100.0 - exceedance, 1)
    return None
