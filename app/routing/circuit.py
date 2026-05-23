import pybreaker
import sentry_sdk

CIRCUIT_FAIL_MAX = 3
CIRCUIT_RESET_TIMEOUT_SECONDS = 3600  # 1 hour — manual reset only during demo

breaker = pybreaker.CircuitBreaker(
    fail_max=CIRCUIT_FAIL_MAX,
    reset_timeout=CIRCUIT_RESET_TIMEOUT_SECONDS,
    name="routing-engine",
)

# Closest reachable neighbor per hospital (within MAX_EDGE_DISTANCE=5.5)
# Path is destination-first to match Dijkstra convention
_FALLBACK_ROUTES: dict[str, dict] = {
    "St. Jude":        {"supplier_id": "City General",    "path": ["St. Jude", "City General"],           "distance": 5.0},
    "City General":    {"supplier_id": "Downtown ER",     "path": ["City General", "Downtown ER"],         "distance": 2.24},
    "Downtown ER":     {"supplier_id": "City General",    "path": ["Downtown ER", "City General"],         "distance": 2.24},
    "Riverside Medical": {"supplier_id": "Downtown ER",   "path": ["Riverside Medical", "Downtown ER"],   "distance": 4.24},
    "Metro Health":    {"supplier_id": "Downtown ER",     "path": ["Metro Health", "Downtown ER"],         "distance": 4.12},
}

_DEFAULT_FALLBACK = _FALLBACK_ROUTES["St. Jude"]


def get_fallback_result(destination: str) -> dict:
    route = _FALLBACK_ROUTES.get(destination, _DEFAULT_FALLBACK)
    return {
        "routes": [{
            "supplier_id": route["supplier_id"],
            "quantity_allocated": 0,
            "path": route["path"],
            "distance": route["distance"],
        }],
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
