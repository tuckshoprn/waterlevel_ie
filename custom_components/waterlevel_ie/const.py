"""Constants for the WaterLevel.ie integration."""
DOMAIN = "waterlevel_ie"

# Configuration
CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL = 15  # minutes

# API
API_URL = "https://waterlevel.ie/geojson/latest/"
API_TIMEOUT = 30  # seconds (increased from 10 for resilience)

# Retry configuration
MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_FACTOR = 2  # Exponential backoff: 1s, 2s, 4s

# Data retention
DATA_RETENTION_HOURS = 24  # Keep last good data for 24 hours during outages

# OPW Station Reference Restrictions
# Per OPW terms: Only stations with reference numbers between 00001 and 41000
# are suitable for republication. Data from stations outside this range should
# not be used or republished without express permission from OPW.
# Source: https://waterlevel.ie/page/api/
STATION_REF_MIN = 1
STATION_REF_MAX = 41000