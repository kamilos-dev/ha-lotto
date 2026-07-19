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

# How many most-recent draws to fetch per game type on each poll when the
# provider can't be queried by date (LottoOpenApiClient only - the default
# LottoPublicApiClient fetches exactly each coupon's own draw window instead).
RESULTS_FETCH_SIZE = 20

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
PANEL_JS_VERSION = "1"
