# WaterLevel.ie Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/tuckshoprn/waterlevel_ie.svg)](https://github.com/tuckshoprn/waterlevel_ie/releases)
[![License](https://img.shields.io/github/license/tuckshoprn/waterlevel_ie.svg)](LICENSE)

A Home Assistant custom integration that provides real-time hydrometric data from [WaterLevel.ie](https://waterlevel.ie/) - Ireland's Office of Public Works (OPW) water monitoring network.

## Features

- 📊 **Multiple Sensor Types**: Water levels, temperatures, flow rates, and ordnance datum readings
- 🌍 **All Irish Stations**: Access data from hundreds of monitoring stations across Ireland
- 📈 **Long-Term Statistics**: Full support for Home Assistant's long-term statistics and history
- 🔄 **Resilient Design**:
  - Automatic retry with exponential backoff
  - 24-hour data retention during API outages
  - Smart error logging to reduce spam
- 🎛️ **Configurable**: Adjustable update interval (5-120 minutes)
- 🔌 **API Status Monitoring**: Binary sensor shows real-time API availability
- 📍 **Location Data**: Each sensor includes GPS coordinates and Google Maps links

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/tuckshoprn/waterlevel_ie`
6. Select category: "Integration"
7. Click "Add"
8. Search for "WaterLevel.ie" in HACS
9. Click "Download"
10. Restart Home Assistant

### Manual Installation

1. Download the latest release from [GitHub](https://github.com/tuckshoprn/waterlevel_ie/releases)
2. Copy the `custom_components/waterlevel_ie` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Configuration

### Adding the Integration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for **WaterLevel.ie**
4. Click to add (no configuration required)

### Configuration Options

After installation, you can configure the integration:

1. Go to **Settings** → **Devices & Services**
2. Find **WaterLevel.ie** and click **Configure**
3. Adjust settings:
   - **Update Interval**: How often to fetch data (5-120 minutes, default: 15)

## Available Sensors

Each hydrometric station can provide multiple sensor types:

| Sensor Type | Description | Unit | Device Class |
|-------------|-------------|------|--------------|
| Water Level | Current water height | m | Distance |
| Water Temperature | Water temperature | °C | Temperature |
| Flow Rate | Water flow rate | m³/s | Volume Flow Rate |
| Ordnance Datum | Height above sea level | - | - |

### Example Sensors

- `sensor.river_shannon_ballyleague_water_level`
- `sensor.river_lee_cork_city_water_temperature`
- `sensor.river_liffey_islandbridge_flow_rate`

### Binary Sensor

- `binary_sensor.waterlevel_ie_api_status`: Shows whether the API is currently online

## Sensor Attributes

Each sensor includes additional attributes:

```yaml
region: Southeast
last_updated: "2026-01-03T10:30:00"
latitude: 52.6652
longitude: -8.6238
location_link: "https://www.google.com/maps/search/?api=1&query=52.6652,-8.6238"
attribution: "Data provided by WaterLevel.ie (OPW)"
using_cached_data: false  # Shows true during API outages
data_age_hours: 0.5  # Only present when using cached data
```

## Resilience Features

### Data Retention
During API outages, the integration retains the last known good data for **24 hours**, ensuring your sensors remain functional even when the upstream service is unavailable.

### Smart Retry Logic
- **3 automatic retry attempts** with exponential backoff (1s, 2s, 4s)
- Distinguishes between temporary server errors (retries) and permanent client errors (no retry)
- Extended timeout (30 seconds) for better reliability

### Reduced Log Spam
- Logs warnings only every 4 failures during extended outages
- Clear notification when API service recovers
- Detailed diagnostic information in attributes

## Long-Term Statistics

All sensors are configured for optimal long-term statistics:

- **State Class**: `measurement`
- **Display Precision**:
  - Water Level: 3 decimals (mm precision)
  - Temperature: 1 decimal (0.1°C)
  - Flow Rate: 3 decimals
  - Ordnance Datum: 2 decimals

Statistics are automatically tracked in Home Assistant's recorder for historical analysis and graphs.

## Automation Examples

### Alert on High Water Level

```yaml
automation:
  - alias: "High Water Level Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.river_shannon_ballyleague_water_level
        above: 3.5
    action:
      - service: notify.mobile_app
        data:
          message: "Warning: River Shannon water level is high ({{ states('sensor.river_shannon_ballyleague_water_level') }}m)"
```

### API Status Notification

```yaml
automation:
  - alias: "WaterLevel.ie API Down"
    trigger:
      - platform: state
        entity_id: binary_sensor.waterlevel_ie_api_status
        to: "off"
        for:
          minutes: 30
    action:
      - service: persistent_notification.create
        data:
          message: "WaterLevel.ie API has been unavailable for 30 minutes. Using cached data."
          title: "Water Level Integration Notice"
```

## Troubleshooting

### No Sensors Appearing

1. Check Home Assistant logs for errors
2. Verify internet connectivity to waterlevel.ie
3. Check the API status binary sensor
4. Try reloading the integration

### Sensors Showing "Unavailable"

- If `binary_sensor.waterlevel_ie_api_status` is "off", the API is currently down
- Check sensor attributes for `using_cached_data` and `data_age_hours`
- Data will be retained for 24 hours during outages

### Outdated Data

1. Check the `last_updated` attribute on your sensor
2. Verify the API status binary sensor
3. Adjust the update interval in integration configuration

## API Information

This integration uses the public API provided by WaterLevel.ie:
- **Endpoint**: `https://waterlevel.ie/geojson/latest/`
- **Format**: GeoJSON
- **Update Frequency**: Configurable (default: 15 minutes)
- **Data Provider**: Office of Public Works (OPW), Ireland

## Support

- **Issues**: [GitHub Issues](https://github.com/tuckshoprn/waterlevel_ie/issues)
- **Documentation**: [WaterLevel.ie](https://waterlevel.ie/)
- **Home Assistant Community**: [Community Forum](https://community.home-assistant.io/)

## Credits

- Data provided by [WaterLevel.ie](https://waterlevel.ie/) - Office of Public Works (OPW)
- Integration developed by [@tuckshoprn](https://github.com/tuckshoprn)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Changelog

### Version 1.2.0 (2026-01-03)

**New Features:**
- Added API status binary sensor for real-time monitoring
- Implemented 24-hour data retention during API outages
- Added configurable update interval (5-120 minutes)
- Enhanced sensor attributes with cached data indicators

**Improvements:**
- Exponential backoff retry logic (3 attempts)
- Smart error logging (reduces spam by 75%)
- Increased API timeout from 10s to 30s
- Added suggested display precision for all sensors
- Better handling of API failures and partial responses

**Bug Fixes:**
- Removed excessive debug logging
- Improved error messages with context

### Version 1.1.0

- Initial public release
- Basic sensor support for all WaterLevel.ie stations
