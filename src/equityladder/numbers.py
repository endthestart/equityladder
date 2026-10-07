"""Strict money and share values. A missing or malformed figure raises; nothing
becomes zero by default."""

from decimal import ROUND_FLOOR, Decimal, InvalidOperation


class LadderError(ValueError):
    """An input the ladder cannot use truthfully, or a state it must not act in."""


def finite(value) -> Decimal:
    """Any finite number, signed (cash, P&L)."""
    if value is None:
        raise LadderError('financial value is unavailable')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise LadderError('financial value is malformed') from exc
    if not result.is_finite():
        raise LadderError('financial value must be finite')
    return result


def nonnegative(value) -> Decimal:
    """A finite number at or above zero (share counts, reserves, fees)."""
    result = finite(value)
    if result < 0:
        raise LadderError('financial value must not be negative')
    return result


def positive(value) -> Decimal:
    """A finite number above zero (prices, steps)."""
    result = finite(value)
    if result <= 0:
        raise LadderError('financial value must be finite and positive')
    return result


def whole(value) -> int:
    """Whole shares in a non-negative quantity, rounded down: a ladder never trades a
    share it cannot fully pay for or fully own."""
    return int(nonnegative(value).to_integral_value(rounding=ROUND_FLOOR))
