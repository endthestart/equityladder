"""Average-cost accounting that keeps adoption separate from profit.

A ladder usually starts from shares already held. Those shares carry gains made
before the ladder existed, so the ladder reports two different things:

* **cost basis** -- realized and unrealized against the shares' average cost,
  including the basis they were adopted with (what a tax view sees);
* **since adoption** -- trade cash plus today's market value, less the value of
  everything handed to the ladder at the time it was handed over (what the ladder
  itself earned).

Shares added later from outside (a recurring purchase deliberately handed to the
ladder) are transfers: they raise the basis and the starting value, never profit.

This is strategy average cost, not a tax-lot report: a broker may match lots
first-in-first-out.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from equityladder.anchor import Side
from equityladder.numbers import LadderError, finite, nonnegative, positive

_ZERO = Decimal('0')
_CENT = Decimal('0.01')


@dataclass(frozen=True, slots=True)
class Adoption:
    shares: Decimal          # shares handed to the ladder when it started
    basis_price: Decimal     # their average acquisition price
    mark: Decimal            # their value per share at the moment of adoption


@dataclass(frozen=True, slots=True)
class Transfer:
    id: str
    shares: Decimal
    basis_price: Decimal
    mark: Decimal
    at: datetime


@dataclass(frozen=True, slots=True)
class Fill:
    """One execution of the ladder's own order, with the fees attributable to it."""
    id: str
    side: Side
    shares: Decimal
    price: Decimal
    fee: Decimal
    executed_at: datetime


@dataclass(frozen=True, slots=True)
class Performance:
    realized: Decimal            # cost basis
    unrealized: Decimal          # cost basis, at the midpoint given
    fees: Decimal
    market_value: Decimal
    owned_shares: Decimal
    remaining_basis: Decimal
    net_trade_cash: Decimal      # positive: the ladder has taken cash out
    since_adoption: Decimal      # excludes gains held at adoption and in transfers
    adoption_value: Decimal      # what was handed over, at its value when handed over


def performance(adoption: Adoption, *, midpoint, transfers: Iterable[Transfer] = (),
                fills: Iterable[Fill] = ()) -> Performance:
    """Both views at ``midpoint``. Raises ``LadderError`` when the order of a buy and a
    sell cannot be known (same timestamp) or a sale exceeds the shares held."""
    quantity = nonnegative(adoption.shares)
    basis = quantity * positive(adoption.basis_price)
    start = quantity * positive(adoption.mark)
    transfers, fills = tuple(transfers), tuple(fills)
    for t in transfers:
        if t.at.tzinfo is None:
            raise LadderError('transfer time must be timezone-aware')
        start += positive(t.shares) * positive(t.mark)
    for f in fills:
        if f.executed_at.tzinfo is None:
            raise LadderError('execution time must be timezone-aware')
    by_time: dict[datetime, set[Side]] = {}
    for f in fills:
        by_time.setdefault(f.executed_at, set()).add(f.side)
    if any(len(sides) > 1 for sides in by_time.values()):
        raise LadderError('buy/sell chronology is ambiguous')
    events = sorted([(t.at, t.id, t) for t in transfers] + [(f.executed_at, f.id, f) for f in fills],
                    key=lambda e: (e[0], e[1]))
    cash = realized = fees = _ZERO
    for _, _, event in events:
        if isinstance(event, Transfer):
            quantity += event.shares
            basis += event.shares * positive(event.basis_price)
            continue
        shares, price, fee = positive(event.shares), positive(event.price), nonnegative(event.fee)
        fees += fee
        if event.side is Side.BUY:
            quantity += shares
            basis += shares * price + fee
            cash -= shares * price + fee
        else:
            if quantity < shares:
                raise LadderError('a sale exceeds the shares held')
            allocated = basis * shares / quantity
            proceeds = shares * price - fee
            realized += proceeds - allocated
            quantity -= shares
            basis -= allocated
            cash += proceeds
    market_value = quantity * positive(midpoint)
    return Performance(realized, market_value - basis, fees, market_value, quantity, basis,
                       cash, cash + market_value - start, start)


def conserves(*, quantity, price, value, net, fee, buy: bool, unit=_CENT) -> bool:
    """Whether a broker's stated trade conserves cash: the stated ``value`` equals
    quantity x price within half the broker's money ``unit`` (an average price finer
    than a cent is rounded there), and ``net`` equals that value less fees exactly.
    ``value`` and ``net`` are signed as cash moves: negative for a buy."""
    gross, cash = finite(value), finite(net)
    expected = positive(quantity) * positive(price) * (-1 if buy else 1)
    return abs(gross - expected) <= positive(unit) / 2 and cash == gross - nonnegative(fee)
