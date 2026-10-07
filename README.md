# equityladder

Dependency-free math for a price-step equity ladder: rest one buy a step below the
last execution and one sell a step above it, in whole shares, and account for the
result without mistaking the shares you started with for profit.

The idea is old and simple. A volatile holding you believe in long term goes up 1%,
you sell a little; it goes down 1%, you buy a little. Over chop you end with more
cash or more shares than you started with, and you never have to watch the screen.
The details are where it goes wrong, and they are what this package is for:

- **The anchor is the last actual execution**, not a fixed grid and not your cost
  basis. After three steps up the ladder buys back on the first step down from the
  peak; it does not wait for the price to return to where you started.
- **Whole shares, rounded down.** One percent of 150.5 shares is one share, not 1.5.
  One percent of 40 shares is nothing, and the ladder says so rather than forcing a
  trade.
- **Ticks.** Limits land on a valid price increment for their price tier, rounded so
  a buy is never higher and a sell never lower than the step asked for.
- **Cash, not buying power.** A buy spends cash the caller has declared free, after
  its own reservations; a margin account will happily lend you the rest, and the
  interest arrives quietly. Borrowing is an explicit allowance or nothing.
- **Adoption is not profit.** A ladder usually starts from shares already held. Those
  shares carry gains made before the ladder existed. Cost-basis P&L includes them;
  P&L *since adoption* does not.

No dependencies: the standard library and `Decimal`. No broker SDK, no network, no
disk. It proposes and accounts; placing, cancelling and reconciling orders is the
caller's job.

```python
from decimal import Decimal as D
from equityladder import LadderSettings, SizingMode, TickTier, propose_pair

settings = LadderSettings(step=D('0.01'), mode=SizingMode.POSITION,
                          trade_fraction=D('0.01'), headroom_divisor=D('100'),
                          max_investment=D('12000'))
us_equity = (TickTier(D('0.0001'), below=D('1')), TickTier(D('0.01')))

pair = propose_pair(settings, owned=D('150.5'), anchor=D('50.00'),
                    tiers=us_equity, free_cash=D('1000'))
print(pair.buy, pair.sell)
# Order(price=Decimal('49.50'), quantity=1) Order(price=Decimal('50.50'), quantity=1)
```

## Sizing

Two modes, chosen per ladder. Both clamp each side independently: a buy to the
investment ceiling and to free cash, a sell to the shares not already reserved by
another working order. The buy is never collateral for the sell.

| Mode | Sell, per step | Buy, per step | Character |
|---|---|---|---|
| `position` | `trade_fraction` of shares held | the same number of shares | never sells the last share, never all-in |
| `headroom` | `1/X` of shares held | `1/X` of the room left under `max_investment` | selling into a rally frees room, so a later dip buys more |

## The anchor

`next_anchor(executions)` decides where the next pair centres once one finishes:

- one side executed: the volume-weighted average of its fills (never the limit
  price, never the order in which fill messages arrived);
- nothing executed: no new anchor;
- both sides executed in one pair (a fast round trip): the last fill is the
  anchor, the average of the executions at the latest execution time.

## Accounting

`performance(adoption, midpoint=..., transfers=..., fills=...)` returns both views
on strategy average cost:

| Field | Meaning |
|---|---|
| `realized`, `unrealized` | against average cost, including the adopted basis |
| `since_adoption` | trade cash + market value − what was handed to the ladder, at its value then |
| `net_trade_cash` | cash the ladder has taken out (positive) or put in |

Shares added from outside later are `Transfer`s: they raise the basis and the
starting value, never profit. This is not a tax-lot report; a broker may match lots
first-in-first-out.

`conserves(...)` checks a broker's stated trade: value equals quantity × price
within half the broker's money unit (a price-improved fill at $50.1234 is stated as
$50.12), and net equals value less fees exactly.

## What it does not do

No order placement, no lifecycle, no recovery from a dropped connection, no
ownership reconciliation: those belong to the application, which knows its broker.
No forecasting and no optimisation of the step or the fraction: those are the
owner's policy, and every `LadderSettings` field is required for that reason.

## License

MIT.
