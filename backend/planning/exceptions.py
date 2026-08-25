class PlanningError(Exception):
    def __init__(self, code: str, message: str, fields: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fields = _normalize_fields(fields)


def _normalize_fields(fields: dict | None) -> dict:
    """DRF-compatible: each field maps to a list of message strings."""
    if not fields:
        return {}
    out: dict = {}
    for key, value in fields.items():
        if isinstance(value, (list, tuple)):
            out[key] = [str(v) for v in value]
        else:
            out[key] = [str(value)]
    return out


class ValidationFailed(PlanningError):
    def __init__(self, message: str, fields: dict | None = None):
        super().__init__("VALIDATION_ERROR", message, fields)


class GeocodeFailed(PlanningError):
    def __init__(self, message: str, fields: dict | None = None):
        super().__init__("GEOCODE_FAILED", message, fields)


class RouteFailed(PlanningError):
    def __init__(self, message: str, fields: dict | None = None):
        super().__init__("ROUTE_FAILED", message, fields)


class PlanIntegrityError(PlanningError):
    def __init__(self, message: str, fields: dict | None = None):
        super().__init__("PLAN_INTEGRITY_ERROR", message, fields)
