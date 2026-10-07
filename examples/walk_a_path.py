"""Walk a ladder over a made-up price path, with no broker.

Each step: propose a pair around the anchor, fill whichever side the next price
crosses (at its limit, a simplification a real broker will not honour), re-anchor
on the execution, and account. Run with ``uv run python examples/walk_a_path.py``.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

from equityladder import (
    Adoption,
    Execution,
    Fill,
    LadderSettings,
    Side,
    SizingMode,
    TickTier,
    next_anchor,
    performance,
    propose_pair,
)

TIERS = (TickTier(D('0.0001'), below=D('1')), TickTier(D('0.01')))
SETTINGS = LadderSettings(step=D('0.01'), mode=SizingMode.POSITION, trade_fraction=D('0.02'),
                          headroom_divisor=D('50'), max_investment=D('20000'))
FEE = D('0.01')
PATH = ['50', '50.6', '51.1', '51.7', '51.0', '50.4', '49.8', '50.3', '50.9', '50.2']

adoption = Adoption(shares=D('200'), basis_price=D('45'), mark=D('50'))
owned, anchor, cash = adoption.shares, D('50'), D('5000')
fills, start = [], datetime(2026, 10, 1, 14, 0, tzinfo=UTC)

for minute, price in enumerate(PATH[1:], start=1):
    price, at = D(price), start + timedelta(minutes=minute)
    pair = propose_pair(SETTINGS, owned=owned, anchor=anchor, tiers=TIERS, free_cash=cash)
    if price <= pair.buy.price and pair.buy.quantity:
        side, order = Side.BUY, pair.buy
    elif price >= pair.sell.price and pair.sell.quantity:
        side, order = Side.SELL, pair.sell
    else:
        print(f'{price:>7}  no fill (buy {pair.buy.price}, sell {pair.sell.price})')
        continue
    fills.append(Fill(f'f{minute}', side, D(order.quantity), order.price, FEE, at))
    owned += order.quantity if side is Side.BUY else -order.quantity
    cash += -order.quantity * order.price - FEE if side is Side.BUY else order.quantity * order.price - FEE
    anchor = next_anchor([Execution(side, D(order.quantity), order.price, at)]).anchor
    print(f'{price:>7}  {side.value:<4} {order.quantity} @ {order.price}  -> anchor {anchor}')

result = performance(adoption, midpoint=D(PATH[-1]), fills=fills)
print(f'\nshares {result.owned_shares}  realized (cost basis) {result.realized:.2f}  '
      f'unrealized {result.unrealized:.2f}')
print(f'since adoption {result.since_adoption:.2f}  vs holding still '
      f'{adoption.shares * (D(PATH[-1]) - adoption.mark):.2f}')
