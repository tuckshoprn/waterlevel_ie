"""Config flow for WaterLevel.ie integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_RIVERS,
    CONF_STATIONS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_RIVERS,
    DEFAULT_STATIONS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .coordinator import _normalise_name
from . import rivers as rivers_mod

_LOGGER = logging.getLogger(__name__)

# Minimum update interval (API updates every 15 minutes)
MIN_UPDATE_INTERVAL = 15
# Maximum update interval (24 hours = 1440 minutes)
MAX_UPDATE_INTERVAL = 1440


def _coerce_selection(raw: Any, available: dict[str, str]) -> list[str]:
    """Return the current selection as a list of station refs.

    Accepts either the new format (a list of refs) or the legacy format (a
    newline-separated string of station names), mapping legacy names to refs
    using the available-station index where possible.
    """
    if isinstance(raw, list):
        # Keep only refs we still know about; if we have no index, keep as-is.
        return [r for r in raw if r in available] if available else list(raw)
    if isinstance(raw, str) and raw.strip():
        # A station name can be shared by more than one station, so map each
        # name to every matching ref rather than a single one.
        name_to_refs: dict[str, list[str]] = {}
        for ref, name in available.items():
            name_to_refs.setdefault(_normalise_name(name), []).append(ref)
        refs: list[str] = []
        for line in raw.splitlines():
            normalised = _normalise_name(line)
            if not normalised:
                continue
            matches = name_to_refs.get(normalised, [])
            if len(matches) > 1:
                _LOGGER.warning(
                    "Station name %r matches %d stations (refs: %s); pre-selecting "
                    "all of them. Refine your choice in the integration options.",
                    line.strip(),
                    len(matches),
                    ", ".join(matches),
                )
            for ref in matches:
                if ref not in refs:
                    refs.append(ref)
        return refs
    return []


class WaterLevelConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for WaterLevel.ie."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial setup step."""
        if user_input is not None:
            # Store the update interval in options (not data)
            return self.async_create_entry(
                title="WaterLevel.ie",
                data={},
                options={CONF_UPDATE_INTERVAL: user_input[CONF_UPDATE_INTERVAL]},
            )

        # Show configuration form with update interval
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=DEFAULT_UPDATE_INTERVAL,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_UPDATE_INTERVAL,
                            max=MAX_UPDATE_INTERVAL,
                            step=1,
                            unit_of_measurement="minutes",
                            mode=selector.NumberSelectorMode.BOX,
                        ),
                    ),
                }
            ),
            description_placeholders={
                "min_interval": str(MIN_UPDATE_INTERVAL),
                "max_interval": str(MAX_UPDATE_INTERVAL),
                "api_update_frequency": "15",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> WaterLevelOptionsFlowHandler:
        """Get the options flow for this handler."""
        return WaterLevelOptionsFlowHandler()


class WaterLevelOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for WaterLevel.ie integration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get current values or use defaults
        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )
        current_raw = self.config_entry.options.get(CONF_STATIONS, DEFAULT_STATIONS)

        # Fetch the list of available stations (ref -> name) from the running
        # coordinator so we can present a searchable picker.
        available: dict[str, str] = {}
        coordinator = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        if coordinator is not None:
            available = await coordinator.async_available_stations()

        schema: dict[Any, Any] = {
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=current_interval,
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_UPDATE_INTERVAL,
                    max=MAX_UPDATE_INTERVAL,
                    step=1,
                    unit_of_measurement="minutes",
                    mode=selector.NumberSelectorMode.BOX,
                ),
            ),
        }

        if available:
            # Map of station ref -> river, for grouping/labelling.
            river_map = await self.hass.async_add_executor_job(
                rivers_mod.station_river_map
            )

            # River-system selector: pick whole rivers to track all their gauges.
            rivers_present = sorted(
                {river_map[r] for r in available if r in river_map}, key=str.lower
            )
            if rivers_present:
                current_rivers = [
                    r
                    for r in self.config_entry.options.get(CONF_RIVERS, DEFAULT_RIVERS)
                    if r in rivers_present
                ]
                schema[
                    vol.Optional(CONF_RIVERS, default=current_rivers)
                ] = selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=r, label=r)
                            for r in rivers_present
                        ],
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=False,
                    )
                )

            # Station selector: one entry per station (all sensors tracked
            # together), labelled "River — Station" and sorted by river so a
            # system's gauges cluster together; unmatched stations sort last.
            def _sort_key(item: tuple[str, str]) -> tuple[str, str]:
                ref, name = item
                river = river_map.get(ref)
                return (river.lower() if river else "~", name.lower())

            options = []
            for ref, name in sorted(available.items(), key=_sort_key):
                river = river_map.get(ref)
                label = f"{river} — {name}" if river else name
                options.append(selector.SelectOptionDict(value=ref, label=label))
            schema[
                vol.Optional(
                    CONF_STATIONS,
                    default=_coerce_selection(current_raw, available),
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=False,
                )
            )
        else:
            # Fallback: the station list could not be fetched (e.g. API down).
            # Keep the legacy free-text box so configuration still works.
            legacy_default = (
                current_raw
                if isinstance(current_raw, str)
                else "\n".join(str(s) for s in current_raw)
                if isinstance(current_raw, list)
                else ""
            )
            schema[
                vol.Optional(CONF_STATIONS, default=legacy_default)
            ] = selector.TextSelector(
                selector.TextSelectorConfig(multiline=True),
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "min_interval": str(MIN_UPDATE_INTERVAL),
                "max_interval": str(MAX_UPDATE_INTERVAL),
                "api_update_frequency": "15",
                "current_interval": str(current_interval),
            },
        )
