"""
Small, defensive coercion helpers for parsing untrusted CSV data.

These never raise - a malformed individual cell should degrade to a
missing value (None), not corrupt the row or abort the import. Row/file
-level validation errors are raised separately by the caller.
"""

from __future__ import annotations

import math


def safe_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null", "-", "n/a"}:
        return None
    try:
        return float(text.replace(",", ""))
    except (TypeError, ValueError):
        return None


def safe_int(value: object) -> int | None:
    parsed = safe_float(value)
    if parsed is None:
        return None
    return int(round(parsed))


def safe_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def normalize_column_name(name: str) -> str:
    """Lowercases and collapses a raw CSV header into a matchable key, e.g. 'Avg Heart Rate' -> 'avg_heart_rate'."""
    cleaned = "".join(ch if ch.isalnum() else " " for ch in name.strip().lower())
    return "_".join(cleaned.split())
