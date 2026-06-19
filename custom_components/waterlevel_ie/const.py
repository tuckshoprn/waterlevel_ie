"""Constants for the WaterLevel.ie integration."""
DOMAIN = "waterlevel_ie"

# Configuration
CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL = 15  # minutes
# OPW asks that data is not fetched more often than once every 15 minutes, so 15
# is the hard minimum. This is the only OPW-driven bound (they have no interest
# in how slowly you poll), enforced in the config flow AND clamped at setup so a
# stored/imported value can never poll faster.
MIN_UPDATE_INTERVAL = 15  # minutes (OPW rate limit)

CONF_STATIONS = "stations"
DEFAULT_STATIONS = ""  # Empty = track all stations

CONF_RIVERS = "rivers"
DEFAULT_RIVERS: list[str] = []  # Empty = no river-based selection

# Setup acknowledgement: installer confirms they have read the OPW usage terms
# and will notify OPW (waterlevel@opw.ie) of their intended usage as a courtesy.
CONF_ACK_OPW_TERMS = "opw_terms_acknowledged"

# OPW contact for the courtesy usage notification (see https://waterlevel.ie/page/api/)
OPW_CONTACT_EMAIL = "waterlevel@opw.ie"

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