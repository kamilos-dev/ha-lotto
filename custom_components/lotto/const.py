"""Constants for the Lotto integration."""
from homeassistant.const import Platform

DOMAIN = "lotto"

PLATFORMS = [Platform.SENSOR]

# Config / options keys
CONF_API_KEY = "api_key"
CONF_POLL_INTERVAL_HOURS = "poll_interval_hours"

DEFAULT_POLL_INTERVAL_HOURS = 4
MIN_POLL_INTERVAL_HOURS = 1
MAX_POLL_INTERVAL_HOURS = 24

# Game types (must match the Lotto Open API `gameType` values)
GAME_LOTTO = "Lotto"
GAME_EUROJACKPOT = "EuroJackpot"
GAME_TYPES = [GAME_LOTTO, GAME_EUROJACKPOT]

# How many most-recent draws to fetch per game type on each poll. Sized
# generously because the primary endpoint (last-results-per-game) may not
# exist on every API version, in which case it falls back to an endpoint
# confirmed NOT to filter by game type server-side - a request for "Lotto"
# can come back full of unrelated, high-frequency games like Keno, so a
# small size risks missing Lotto/EuroJackpot draws entirely.
RESULTS_FETCH_SIZE = 100

# Coupon status
STATUS_ACTIVE = "active"
STATUS_EXPIRED = "expired"

# Events
EVENT_WIN = "lotto_win"
EVENT_UPDATED = "lotto_updated"

# Storage
STORAGE_VERSION = 1
STORAGE_KEY = "lotto.coupons"

# Panel
PANEL_URL_PATH = "lotto"
PANEL_TITLE = "Lotto"
PANEL_ICON = "mdi:ticket-confirmation-outline"
PANEL_JS_VERSION = "2"
