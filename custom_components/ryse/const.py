DOMAIN = "ryse"

HARDCODED_UUIDS = {
    "rx_uuid": "a72f2801-b0bd-498b-b4cd-4a3901388238",
    "tx_uuid": "a72f2802-b0bd-498b-b4cd-4a3901388238",
}

# Connection and polling configuration
# These can be overridden via config entry options in the future
DEFAULT_CONNECTION_TIMEOUT = 10  # seconds (initial attempt)
DEFAULT_MAX_RETRY_ATTEMPTS = 3
DEFAULT_POLL_INTERVAL = 300  # seconds (5 minutes - rely on advertisements primarily)
DEFAULT_INIT_TIMEOUT = 30  # seconds (wait for first advertisement)