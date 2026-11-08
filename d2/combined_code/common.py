"""Shared parsing helpers for scenario values."""


def parse_bool(value, default=False):
    """Parse booleans from JSON and CSV-style scenario values without truthiness traps."""
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off", ""}:
        return False
    raise ValueError(f"Invalid boolean value {value!r}; expected true or false")
