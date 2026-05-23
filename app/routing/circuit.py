import pybreaker
import sentry_sdk

CIRCUIT_FAIL_MAX = 3
CIRCUIT_RESET_TIMEOUT_SECONDS = 30

breaker = pybreaker.CircuitBreaker(
    fail_max=CIRCUIT_FAIL_MAX,
    reset_timeout=CIRCUIT_RESET_TIMEOUT_SECONDS,
    name="routing-engine",
)

STATIC_FALLBACK_PATH: dict = {
    "routes": [
        {
            "supplier_id": "FALLBACK",
            "quantity_allocated": 0,
            "path": ["St. Jude", "City General"],
            "distance": 0.0,
        }
    ],
    "total_quantity": 0,
    "partial": False,
    "fallback": True,
}


def toggle_breaker() -> None:
    breaker.open()
    sentry_sdk.capture_message(
        "StatRoute circuit breaker manually tripped to OPEN",
        level="warning",
    )


def reset_breaker() -> None:
    breaker.close()
