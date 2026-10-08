"""The next buy/sell pair around an anchor.

The ladder rests one buy a step below the anchor and one sell a step above it. The
anchor is the price of the last actual execution (see ``anchor``), so the ladder
follows the market rather than a fixed grid: after three steps up it buys back on
the first step down from the peak, not on the way back to the original cost.

Two ways to size each side, both in whole shares rounded down:

``position``
    Each side trades ``trade_fraction`` of the shares held. One percent of the
    position on every one-percent move never sells the last share and never buys
    more than a sliver.

``headroom``
    Sells ``1 / headroom_divisor`` of the shares held; buys ``1 / headroom_divisor``
    of the room left under ``max_investment`` at the buy price. Selling into a rally
    frees room, so a later dip buys more.

A ``Skew`` replaces both quantities with fixed share counts while the holding is on
the far side of a target: sell 2 / buy 1 above it works a position down, buy 2 /
sell 1 below it builds one, and the skew ends once the target is reached.

Both sides are then clamped: a buy to the investment ceiling and to the cash the
caller says is free for it, a sell to the shares not already reserved by another
working order. A side can come out at zero shares; that is an answer, not an error.
The buy is never collateral for the sell or the reverse.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from equityladder.numbers import LadderError, finite, nonnegative, positive, whole
from equityladder.ticks import TickTier, round_to_tick

_ZERO = Decimal('0')


class SizingMode(StrEnum):
    POSITION = 'position'
    HEADROOM = 'headroom'


@dataclass(frozen=True, slots=True)
class Skew:
    """Fixed whole-share quantities toward a target holding."""
    buy: int
    sell: int
    target: Decimal

    def __post_init__(self):
        if (type(self.buy) is not int or type(self.sell) is not int
                or self.buy < 0 or self.sell < 0 or not (self.buy or self.sell)):
            raise LadderError('a skew buys and sells whole shares, at least one of them')
        nonnegative(self.target)

    def active(self, owned: Decimal) -> bool:
        """Sell-heavy while above the target, buy-heavy while below, even always."""
        lean = self.buy - self.sell
        return lean == 0 or (lean < 0 and owned > self.target) or (lean > 0 and owned < self.target)


@dataclass(frozen=True, slots=True)
class LadderSettings:
    """One ladder's parameters. Every field is a policy choice; none has a default,
    except ``skew``, which is off unless given."""
    step: Decimal               # fraction of the anchor between anchor and each order
    mode: SizingMode
    trade_fraction: Decimal     # position mode: fraction of held shares per side
    headroom_divisor: Decimal   # headroom mode: X in "1/X of the shares or the room"
    max_investment: Decimal     # ceiling on the holding's value at the buy price
    skew: Skew | None = None

    def __post_init__(self):
        step, fraction = positive(self.step), positive(self.trade_fraction)
        divisor = positive(self.headroom_divisor)
        nonnegative(self.max_investment)
        if step >= 1 or fraction > 1 or divisor < 1:
            raise LadderError('invalid ladder sizing parameters')
        if not isinstance(self.mode, SizingMode):
            raise LadderError(f'unknown sizing mode {self.mode!r}')


@dataclass(frozen=True, slots=True)
class Order:
    price: Decimal      # per share, on a valid tick
    quantity: int       # whole shares; zero means no order on this side


@dataclass(frozen=True, slots=True)
class Pair:
    buy: Order
    sell: Order
    anchor: Decimal
    owned_shares: Decimal
    mode: SizingMode
    skewed: bool = False        # the skew's quantities were used for this pair


def propose_pair(settings: LadderSettings, *, owned, anchor, tiers: Iterable[TickTier],
                 free_cash, reserved_shares=_ZERO) -> Pair:
    """The pair to rest next. ``owned`` may be fractional (a residual from elsewhere);
    orders are whole shares. ``free_cash`` is what the caller allows the buy to spend,
    after its own reservations; a negative figure means nothing is free."""
    quantity, anchor = nonnegative(owned), positive(anchor)
    tiers = tuple(tiers)
    buy = round_to_tick(anchor * (1 - settings.step), tiers, buy=True)
    sell = round_to_tick(anchor * (1 + settings.step), tiers, buy=False)
    if not buy < anchor < sell:
        raise LadderError('ladder prices collapse after tick rounding')
    room = max(_ZERO, nonnegative(settings.max_investment) - quantity * buy)
    if settings.mode is SizingMode.POSITION:
        buy_quantity = sell_quantity = whole(quantity * settings.trade_fraction)
    else:
        sell_quantity = whole(quantity / settings.headroom_divisor)
        buy_quantity = whole(room / (settings.headroom_divisor * buy))
    skewed = settings.skew is not None and settings.skew.active(quantity)
    if skewed:
        buy_quantity, sell_quantity = settings.skew.buy, settings.skew.sell
    buy_quantity = min(buy_quantity, whole(room / buy),
                       whole(max(_ZERO, finite(free_cash)) / buy))
    sell_quantity = min(sell_quantity,
                        whole(max(_ZERO, quantity - nonnegative(reserved_shares))))
    return Pair(Order(buy, buy_quantity), Order(sell, sell_quantity), anchor, quantity,
                settings.mode, skewed)
