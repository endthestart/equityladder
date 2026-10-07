"""Price increments that depend on the price, as exchanges and brokers publish them.

A tier applies to prices strictly below its ``below`` threshold; the tier with the
lowest qualifying threshold wins, and a tier with no threshold is the default above
every threshold. US equities, for example, trade in $0.0001 below $1 and $0.01 at or
above it::

    tiers = (TickTier(Decimal('0.0001'), below=Decimal('1')), TickTier(Decimal('0.01')))

Buys round down and sells round up, so rounding never makes a limit more aggressive
than the ladder step asked for.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from equityladder.numbers import LadderError, positive


@dataclass(frozen=True, slots=True)
class TickTier:
    increment: Decimal
    below: Decimal | None = None      # None: the default tier, above every threshold


def _increment(price: Decimal, tiers: tuple[TickTier, ...]) -> Decimal:
    applicable = [tier for tier in tiers if tier.below is not None and price < tier.below]
    if applicable:
        return min(applicable, key=lambda tier: tier.below).increment
    defaults = [tier for tier in tiers if tier.below is None]
    if not defaults:
        raise LadderError('no tick increment applies at this price')
    return defaults[0].increment


def round_to_tick(price, tiers: Iterable[TickTier], *, buy: bool) -> Decimal:
    """``price`` on a valid tick: down for a buy, up for a sell."""
    tiers = tuple(tiers)
    if sum(1 for tier in tiers if tier.below is None) > 1:
        raise LadderError('more than one default tick tier')
    for tier in tiers:
        positive(tier.increment)
        if tier.below is not None:
            positive(tier.below)
    price = positive(price)
    rounding = ROUND_FLOOR if buy else ROUND_CEILING
    increment = _increment(price, tiers)
    result = (price / increment).to_integral_value(rounding=rounding) * increment
    # Rounding can cross into another tier, whose increment must hold too.
    crossed = _increment(result, tiers)
    if crossed != increment:
        result = (result / crossed).to_integral_value(rounding=rounding) * crossed
    return positive(result)
