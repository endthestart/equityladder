"""What a ladder buy may spend: cash, never borrowing by accident.

Buying power is not cash. A margin account will happily let a ladder buy with
borrowed money, and the interest lands quietly. The funding rule here starts from
the cash balance and subtracts what is already spoken for:

* ``reserved``      -- obligations the account must keep cash for (for example the
                       worst-case settlement of options it holds);
* ``working_debits``-- other working buy orders, fees included;
* ``outgoing``      -- cash already on its way out (withdrawals, pending debits).

``honour_reserve=False`` releases the reservation; a positive ``debit_allowance``
permits borrowing up to that amount, and also releases the reservation, since
protected cash is used before actual borrowing. Both are deliberate overrides, and
``reserve_overridden`` says so.
"""

from dataclasses import dataclass
from decimal import Decimal

from equityladder.numbers import LadderError, finite, nonnegative

_ZERO = Decimal('0')


@dataclass(frozen=True, slots=True)
class Funding:
    normal_available: Decimal    # cash less every reservation
    available: Decimal           # what the buy may actually spend
    reserve_overridden: bool


def available_cash(*, cash, reserved, working_debits, outgoing, debit_allowance=_ZERO,
                   honour_reserve: bool = True) -> Funding:
    if type(honour_reserve) is not bool:
        raise LadderError('the reserve decision must be an explicit boolean')
    cash = finite(cash)
    reserved, working = nonnegative(reserved), nonnegative(working_debits)
    outgoing, allowance = nonnegative(outgoing), nonnegative(debit_allowance)
    normal = cash - reserved - working - outgoing
    expanded = cash + allowance - working - outgoing
    overridden = not honour_reserve or allowance > 0
    return Funding(max(_ZERO, normal), max(_ZERO, expanded if overridden else normal),
                   overridden)
