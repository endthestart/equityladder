"""Average cost, adoption and the anchor, worked by hand."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from equityladder import (
    Adoption,
    AnchorStatus,
    Execution,
    Fill,
    LadderError,
    Side,
    Transfer,
    available_cash,
    conserves,
    next_anchor,
    performance,
)

T0 = datetime(2026, 10, 2, 14, 0, tzinfo=UTC)
ADOPTION = Adoption(shares=D('150'), basis_price=D('40'), mark=D('50'))


def test_adoption_is_not_profit():
    """Shares bought at $40 and adopted at $50: cost basis shows the $10 gain, the
    ladder's own result is zero until it trades or the price moves."""
    result = performance(ADOPTION, midpoint='50')
    assert result.unrealized == D('1500') and result.since_adoption == 0
    assert result.adoption_value == D('7500')


def test_a_sale_realizes_against_average_cost_and_the_ladder_keeps_only_its_own_gain():
    """Sell one share at $50.50 with a $0.01 fee: $50.49 against $40 of basis is $10.49
    realized on a cost basis; since adoption the ladder earned $0.49 of it."""
    sale = Fill('t1', Side.SELL, D('1'), D('50.5'), D('0.01'), T0)
    result = performance(ADOPTION, midpoint='50', fills=[sale])
    assert result.realized == D('10.49') and result.unrealized == D('1490')
    assert result.since_adoption == D('0.49')
    assert result.net_trade_cash + result.market_value - result.adoption_value == D('0.49')


def test_a_later_transfer_raises_the_basis_and_the_start_never_the_profit():
    sale = Fill('t1', Side.SELL, D('1'), D('50.5'), D('0.01'), T0)
    bought_outside = Transfer('recurring-1', D('2'), D('49'), D('50'), T0 + timedelta(hours=1))
    result = performance(ADOPTION, midpoint='50', fills=[sale], transfers=[bought_outside])
    assert result.owned_shares == D('151')
    assert result.realized == D('10.49') and result.unrealized == D('1492')
    assert result.since_adoption == D('0.49')


def test_a_round_trip_harvests_the_wiggle():
    """Sell one at $50.50, buy it back at $50.00, each with fees: one more dollar of
    cash on the same shares."""
    fills = [Fill('s', Side.SELL, D('1'), D('50.5'), D('0.011'), T0),
             Fill('b', Side.BUY, D('1'), D('50'), D('0.001'), T0 + timedelta(minutes=5))]
    result = performance(ADOPTION, midpoint='50', fills=fills)
    assert result.owned_shares == D('150') and result.net_trade_cash == D('0.488')
    assert result.since_adoption == D('0.488') and result.fees == D('0.012')


def test_unknowable_order_and_oversold_shares_are_refused():
    same = [Fill('s', Side.SELL, D('1'), D('50.5'), D('0.01'), T0),
            Fill('b', Side.BUY, D('1'), D('50'), D('0.001'), T0)]
    with pytest.raises(LadderError, match='chronology'):
        performance(ADOPTION, midpoint='50', fills=same)
    with pytest.raises(LadderError, match='exceeds'):
        performance(Adoption(D('1'), D('40'), D('50')), midpoint='50',
                    fills=[Fill('s', Side.SELL, D('2'), D('50'), D('0'), T0)])


def test_the_anchor_follows_actual_executions_only():
    one = next_anchor([Execution(Side.SELL, D('1'), D('49.05'), T0),
                       Execution(Side.SELL, D('2'), D('49.08'), T0 + timedelta(seconds=1))])
    assert one.status is AnchorStatus.ADVANCED and one.anchor == D('49.07')
    assert next_anchor([]).status is AnchorStatus.NO_EXECUTION
    both = next_anchor([Execution(Side.SELL, D('1'), D('49.05'), T0),
                        Execution(Side.BUY, D('1'), D('48.10'), T0 + timedelta(minutes=3))])
    assert both.status is AnchorStatus.BOTH_SIDES and both.anchor == D('48.10')   # the last fill


def test_a_sub_penny_fill_conserves_in_the_brokers_cents():
    """One share at $50.1234 (price improvement): the broker states value −$50.12 and
    net −$50.121 with a $0.001 fee. A cent off in either identity does not conserve."""
    trade = dict(quantity='1', price='50.1234', fee='0.001', buy=True)
    assert conserves(value='-50.12', net='-50.121', **trade)
    assert not conserves(value='-50.13', net='-50.131', **trade)
    assert not conserves(value='-50.12', net='-50.131', **trade)
    assert conserves(quantity='1', price='49.055', value='49.055', net='49.044', fee='0.011',
                     buy=False)


def test_funding_spends_cash_not_buying_power():
    args = dict(cash='1000', reserved='700', working_debits='100', outgoing='50')
    normal = available_cash(**args)
    assert normal.available == D('150') and not normal.reserve_overridden
    expanded = available_cash(**args, debit_allowance='200')
    assert expanded.available == D('1050') and expanded.reserve_overridden
    released = available_cash(cash='6204.17', reserved='8000', working_debits='2298.24',
                              outgoing='0', honour_reserve=False)
    assert released.available == D('3905.93') and released.normal_available == 0
    assert available_cash(cash='-1', reserved='0', working_debits='0', outgoing='0').available == 0
    with pytest.raises(LadderError, match='boolean'):
        available_cash(**args, honour_reserve='false')
