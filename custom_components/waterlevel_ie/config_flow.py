"""Config flow for WaterLevel.ie integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import CONF_STATIONS, CONF_UPDATE_INTERVAL, DEFAULT_STATIONS, DEFAULT_UPDATE_INTERVAL, DOMAIN
from .coordinator import _normalise_name

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
        name_to_ref = {_normalise_name(name): ref for ref, name in available.items()}
        refs: list[str] = []
        for line in raw.splitlines():
            normalised = _normalise_name(line)
            if not normalised:
                continue
            ref = name_to_ref.get(normalised)
            if ref:
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
            # Searchable multi-select, one entry per station (all its sensors
            # are tracked together). Sorted alphabetically by name.
            options = [
                selector.SelectOptionDict(value=ref, label=name)
                for ref, name in sorted(available.items(), key=lambda kv: kv[1].lower())
            ]
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
