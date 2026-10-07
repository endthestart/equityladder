"""Where the ladder centres next: only on what actually executed.

After a pair finishes, the new anchor is the volume-weighted average price of the
side that executed. Never the limit price, never the order in which fill messages
arrived, and never a guess:

* one side executed  -> advance to that side's execution average;
* nothing executed   -> no new anchor; something ended the pair without a trade;
* both sides executed (a fast round trip) -> the last fill is the anchor: the
  average of the executions at the latest execution time.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from equityladder.numbers import LadderError, positive


class Side(StrEnum):
    BUY = 'buy'
    SELL = 'sell'


@dataclass(frozen=True, slots=True)
class Execution:
    side: Side
    quantity: Decimal
    price: Decimal
    executed_at: datetime


class AnchorStatus(StrEnum):
    ADVANCED = 'advanced'
    NO_EXECUTION = 'no_execution'
    BOTH_SIDES = 'both_sides'


@dataclass(frozen=True, slots=True)
class AnchorOutcome:
    status: AnchorStatus
    anchor: Decimal | None              # None only when nothing executed


def next_anchor(executions: Iterable[Execution]) -> AnchorOutcome:
    executions = tuple(executions)
    for e in executions:
        positive(e.quantity)
        positive(e.price)
        if e.executed_at.tzinfo is None:
            raise LadderError('execution time must be timezone-aware')
    sides = {e.side for e in executions}
    if not sides:
        return AnchorOutcome(AnchorStatus.NO_EXECUTION, None)
    status = AnchorStatus.ADVANCED
    if len(sides) > 1:
        latest = max(e.executed_at for e in executions)
        executions = tuple(e for e in executions if e.executed_at == latest)
        status = AnchorStatus.BOTH_SIDES
    shares = sum((e.quantity for e in executions), Decimal('0'))
    average = sum((e.quantity * e.price for e in executions), Decimal('0')) / shares
    return AnchorOutcome(status, average)
