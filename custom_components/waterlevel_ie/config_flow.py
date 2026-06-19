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
    CONF_ACK_OPW_TERMS,
    CONF_RIVERS,
    CONF_STATIONS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_RIVERS,
    DEFAULT_STATIONS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MIN_UPDATE_INTERVAL,
)
from .coordinator import _normalise_name
from . import rivers as rivers_mod

_LOGGER = logging.getLogger(__name__)


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
        """Show the OPW data usage terms; submitting continues to setup."""
        if user_input is not None:
            return await self.async_step_acknowledge()

        # Informational step: terms only, with a submit ("continue") button.
        # URLs must be supplied as placeholders (hassfest forbids URLs in strings).
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            description_placeholders={
                "cc_by_url": "https://creativecommons.org/licenses/by/4.0/",
                "source_url": "http://waterlevel.ie",
                "terms_url": "https://waterlevel.ie/page/api/",
            },
        )

    async def async_step_acknowledge(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Collect the update interval and require acknowledgement of the terms."""
        errors: dict[str, str] = {}
        # Default the interval field; preserve the user's entry when re-showing
        # the form after a validation error.
        interval_default = DEFAULT_UPDATE_INTERVAL
        if user_input is not None:
            interval_default = user_input.get(
                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
            )
            if not user_input.get(CONF_ACK_OPW_TERMS):
                # OPW asks data users to notify them of their usage as a courtesy;
                # require the installer to acknowledge this before proceeding.
                errors["base"] = "opw_terms_not_acknowledged"
            else:
                # Store the update interval in options (not data)
                return self.async_create_entry(
                    title="WaterLevel.ie",
                    data={},
                    options={
                        CONF_UPDATE_INTERVAL: user_input[CONF_UPDATE_INTERVAL]
                    },
                )

        # Show configuration form with update interval and the acknowledgement.
        return self.async_show_form(
            step_id="acknowledge",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=interval_default,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_UPDATE_INTERVAL,
                            step=1,
                            unit_of_measurement="minutes",
                            mode=selector.NumberSelectorMode.BOX,
                        ),
                    ),
                    vol.Required(
                        CONF_ACK_OPW_TERMS,
                        default=False,
                    ): selector.BooleanSelector(),
                }
            ),
            errors=errors,
            description_placeholders={
                "min_interval": str(MIN_UPDATE_INTERVAL),
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
                "api_update_frequency": "15",
                "current_interval": str(current_interval),
            },
        )
