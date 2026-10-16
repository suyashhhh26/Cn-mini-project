"""
Network Monitor — Input Validators
Validates IP addresses, hostnames, device fields, and settings.
"""

import ipaddress
import re
import logging

logger = logging.getLogger(__name__)

# RFC 952 / RFC 1123 hostname label pattern
_HOSTNAME_LABEL = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$")

ALLOWED_DEVICE_TYPES = {"Router", "Server", "Computer", "Switch", "Printer", "Other"}


# ─── IP / Hostname ────────────────────────────────────────────────────────────

def is_valid_ip(value: str) -> bool:
    """Return True if value is a valid IPv4 or IPv6 address."""
    try:
        ipaddress.ip_address(value.strip())
        return True
    except ValueError:
        return False


def is_valid_hostname(value: str) -> bool:
    """
    Return True if value is a valid hostname.
    Accepts labels separated by dots; each label must match RFC 1123.
    Total length must not exceed 253 characters.
    """
    hostname = value.strip().rstrip(".")
    if not hostname or len(hostname) > 253:
        return False
    labels = hostname.split(".")
    # If all parts are digits, it's an IP-like string, not a hostname
    if all(label.isdigit() for label in labels):
        return False
    # Multi-label hostnames cannot have an all-numeric top-level domain (RFC 1123 / RFC 3696)
    if len(labels) > 1 and labels[-1].isdigit():
        return False
    return all(_HOSTNAME_LABEL.match(label) for label in labels)


def is_valid_target(value: str) -> tuple[bool, str]:
    """
    Validate a monitoring target (IP address or hostname).
    Returns (is_valid, normalized_target).
    """
    target = value.strip().lower()
    if not target:
        return False, ""
    if is_valid_ip(target):
        return True, target
    if is_valid_hostname(target):
        return True, target
    return False, ""


def normalize_target(value: str) -> str:
    """Strip and lowercase a target string."""
    return value.strip().lower()


# ─── Device Fields ────────────────────────────────────────────────────────────

class ValidationError(Exception):
    """Raised when input validation fails."""
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def validate_device_payload(data: dict, is_update: bool = False) -> dict:
    """
    Validate and normalise a device creation or update payload.

    Args:
        data: Raw request dict.
        is_update: If True, only fields present in data are validated.

    Returns:
        Cleaned data dict.

    Raises:
        ValidationError on the first invalid field encountered.
    """
    cleaned: dict = {}

    # name
    if "name" in data or not is_update:
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValidationError("name", "Device name is required.")
        if len(name) > 100:
            raise ValidationError("name", "Device name must be 100 characters or fewer.")
        cleaned["name"] = name

    # target
    if "target" in data or not is_update:
        raw_target = str(data.get("target", "")).strip()
        ok, target = is_valid_target(raw_target)
        if not ok:
            raise ValidationError(
                "target",
                f"'{raw_target}' is not a valid IPv4 address, IPv6 address, or hostname.",
            )
        cleaned["target"] = target

    # device_type
    if "device_type" in data:
        dt = str(data["device_type"]).strip()
        if dt not in ALLOWED_DEVICE_TYPES:
            raise ValidationError(
                "device_type",
                f"Device type must be one of: {', '.join(sorted(ALLOWED_DEVICE_TYPES))}.",
            )
        cleaned["device_type"] = dt
    elif not is_update:
        cleaned["device_type"] = "Other"

    # location
    if "location" in data:
        loc = str(data["location"]).strip()
        if len(loc) > 200:
            raise ValidationError("location", "Location must be 200 characters or fewer.")
        cleaned["location"] = loc
    elif not is_update:
        cleaned["location"] = ""

    # description
    if "description" in data:
        desc = str(data["description"]).strip()
        if len(desc) > 500:
            raise ValidationError("description", "Description must be 500 characters or fewer.")
        cleaned["description"] = desc
    elif not is_update:
        cleaned["description"] = ""

    # monitoring_interval
    if "monitoring_interval" in data:
        try:
            interval = int(data["monitoring_interval"])
        except (TypeError, ValueError):
            raise ValidationError("monitoring_interval", "Monitoring interval must be an integer.")
        if not (5 <= interval <= 300):
            raise ValidationError(
                "monitoring_interval",
                "Monitoring interval must be between 5 and 300 seconds.",
            )
        cleaned["monitoring_interval"] = interval
    elif not is_update:
        cleaned["monitoring_interval"] = 30

    # is_monitoring_enabled
    if "is_monitoring_enabled" in data:
        val = data["is_monitoring_enabled"]
        if isinstance(val, bool):
            cleaned["is_monitoring_enabled"] = 1 if val else 0
        elif isinstance(val, int) and val in (0, 1):
            cleaned["is_monitoring_enabled"] = val
        else:
            raise ValidationError("is_monitoring_enabled", "is_monitoring_enabled must be true or false.")

    return cleaned


# ─── Settings Validation ──────────────────────────────────────────────────────

SETTINGS_SCHEMA: dict[str, dict] = {
    "default_monitoring_interval": {"type": int, "min": 5,  "max": 300},
    "default_ping_timeout":        {"type": int, "min": 1,  "max": 30},
    "max_concurrent_probes":       {"type": int, "min": 1,  "max": 50},
    "data_retention_days":         {"type": int, "min": 1,  "max": 365},
    "dashboard_refresh_interval":  {"type": int, "min": 1000, "max": 60000},
}


def validate_setting(key: str, value: str) -> tuple[bool, str]:
    """
    Validate a setting key/value pair.
    Returns (is_valid, error_message).
    """
    if key not in SETTINGS_SCHEMA:
        return False, f"Unknown setting key: '{key}'."
    schema = SETTINGS_SCHEMA[key]
    try:
        casted = schema["type"](value)
    except (ValueError, TypeError):
        return False, f"Setting '{key}' must be a valid {schema['type'].__name__}."
    if "min" in schema and casted < schema["min"]:
        return False, f"Setting '{key}' must be at least {schema['min']}."
    if "max" in schema and casted > schema["max"]:
        return False, f"Setting '{key}' must be at most {schema['max']}."
    return True, ""
