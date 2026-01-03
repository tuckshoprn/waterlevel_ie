# WaterLevel.ie Integration

Monitor water levels, temperatures, and flow rates from Ireland's national hydrometric network.

## About

This integration connects Home Assistant to [WaterLevel.ie](https://waterlevel.ie/), the Office of Public Works (OPW) national water monitoring service for Ireland. Get real-time data from hundreds of monitoring stations across the country.

## Key Features

- **Multiple Sensor Types**: Water levels, temperatures, flow rates, and ordnance datum
- **All Irish Stations**: Automatic discovery of all available monitoring stations
- **Resilient**: 24-hour data retention, automatic retry, smart error handling
- **Configurable**: Adjustable update intervals
- **Statistics Ready**: Full long-term statistics support
- **Location Aware**: GPS coordinates and map links for each station

## Quick Start

1. Install via HACS
2. Restart Home Assistant
3. Add the WaterLevel.ie integration (Settings → Devices & Services)
4. Sensors will appear automatically for all available stations

## What You Get

Each monitoring station creates a device with multiple sensors:

- Water Level (meters)
- Water Temperature (°C)
- Flow Rate (m³/s)
- Ordnance Datum

Plus a diagnostic binary sensor showing API status.

## Perfect For

- Flood monitoring and alerts
- Environmental monitoring
- Water quality tracking
- Historical trend analysis
- Local river/lake monitoring

## Data Source

All data comes from WaterLevel.ie, operated by Ireland's Office of Public Works (OPW). This integration simply makes that public data available in Home Assistant.
