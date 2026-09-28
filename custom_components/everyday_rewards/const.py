"""Constants for the Everyday Rewards integration."""

DOMAIN = "everyday_rewards"

CONF_CARD_NUMBER = "card_number"
CONF_HASHED_CRN = "hashed_crn"
CONF_SCAN_INTERVAL_HOURS = "scan_interval_hours"
CONF_AUTO_BOOST = "auto_boost"

DEFAULT_SCAN_INTERVAL_HOURS = 6
DEFAULT_AUTO_BOOST = True

EVENT_BOOSTED = "everyday_rewards_boosted"
SERVICE_BOOST_ALL = "boost_all"
ISSUE_ACCESS_DENIED = "api_access_denied"
