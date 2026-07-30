"""Reusable validation primitives for project and runtime parameters."""

import math


def finite_number(value, name, *, positive=False, nonnegative=False, maximum=None):
    """Return a finite float after applying common range constraints."""
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if positive and result <= 0.0:
        raise ValueError(f"{name} must be positive")
    if nonnegative and result < 0.0:
        raise ValueError(f"{name} must be non-negative")
    if maximum is not None and result > float(maximum):
        raise ValueError(f"{name} must be at most {maximum}")
    return result


def integer(value, name, *, minimum=None, maximum=None):
    """Return an integer after validating finiteness and optional bounds."""
    converted = finite_number(value, name)
    if converted != round(converted):
        raise ValueError(f"{name} must be an integer")
    result = int(converted)
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return result


def clamp01(value, default=None):
    """Clamp a number to 0..1, optionally falling back for invalid input."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        if default is None:
            raise
        number = float(default)
    if not math.isfinite(number):
        if default is None:
            return number
        number = float(default)
    return float(min(max(number, 0.0), 1.0))
