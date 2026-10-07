"""Known prices and share counts, worked by hand."""

from decimal import Decimal as D

import pytest

from equityladder import (
    LadderError,
    LadderSettings,
    Order,
    SizingMode,
    TickTier,
    finite,
    positive,
    propose_pair,
    round_to_tick,
    whole,
)

TIERS = (TickTier(D('0.0001'), below=D('1')), TickTier(D('0.01')))


def settings(**changes):
    base = dict(step=D('0.01'), mode=SizingMode.POSITION, trade_fraction=D('0.01'),
                headroom_divisor=D('100'), max_investment=D('12000'))
    return LadderSettings(**{**base, **changes})


def test_one_percent_of_a_fractional_holding_is_whole_shares_without_forcing_a_trade():
    """150.5 shares around $50: one percent is 1.505 shares, so one share a side."""
    pair = propose_pair(settings(), owned='150.5', anchor='50', tiers=TIERS, free_cash='1000')
    assert pair.buy == Order(D('49.50'), 1) and pair.sell == Order(D('50.50'), 1)
    small = propose_pair(settings(), owned='40', anchor='50', tiers=TIERS, free_cash='1000')
    assert small.buy.quantity == small.sell.quantity == 0


def test_headroom_sizes_buys_from_room_and_sells_from_shares():
    """100 shares, anchor $50, ceiling $12,000: room at $49.50 is $7,050, a hundredth
    of it buys one share; a hundredth of the shares sells one."""
    pair = propose_pair(settings(mode=SizingMode.HEADROOM), owned='100', anchor='50',
                        tiers=TIERS, free_cash='1000')
    assert pair.buy == Order(D('49.50'), 1) and pair.sell.quantity == 1


def test_clamps_never_spend_a_hypothetical_sale_or_sell_reserved_shares():
    pair = propose_pair(settings(), owned='200', anchor='50', tiers=TIERS, free_cash='49',
                        reserved_shares='199.5')
    assert pair.buy.quantity == pair.sell.quantity == 0
    at_ceiling = propose_pair(settings(max_investment=D('9900')), owned='200', anchor='50',
                              tiers=TIERS, free_cash='10000')
    assert at_ceiling.buy.quantity == 0
    no_cash = propose_pair(settings(), owned='200', anchor='50', tiers=TIERS, free_cash='-5')
    assert no_cash.buy.quantity == 0 and no_cash.sell.quantity == 2


def test_ticks_round_toward_a_less_aggressive_limit_and_respect_tiers():
    assert round_to_tick('48.5992', TIERS, buy=True) == D('48.59')
    assert round_to_tick('48.5901', TIERS, buy=False) == D('48.60')
    assert round_to_tick('0.99999', TIERS, buy=False) == D('1')
    assert round_to_tick('0.12345', TIERS, buy=True) == D('0.1234')
    with pytest.raises(LadderError, match='no tick increment'):
        round_to_tick('10', (), buy=True)
    with pytest.raises(LadderError, match='more than one default'):
        round_to_tick('10', (TickTier(D('0.01')), TickTier(D('0.05'))), buy=True)


@pytest.mark.parametrize('changes', [dict(step=D('1')), dict(trade_fraction=D('1.5')),
                                     dict(headroom_divisor=D('0.5')), dict(mode='position'),
                                     dict(max_investment=D('-1'))])
def test_invalid_settings_are_refused(changes):
    with pytest.raises(LadderError):
        settings(**changes)


@pytest.mark.parametrize('value', [None, 'NaN', 'Infinity', '-1', 'broken', '0'])
def test_unknown_or_invalid_money_is_never_zero(value):
    with pytest.raises(LadderError):
        positive(value)


def test_numbers_are_strict_but_honest():
    assert finite('-3.5') == D('-3.5') and whole('3.99') == 3
    with pytest.raises(LadderError):
        whole('-1')
