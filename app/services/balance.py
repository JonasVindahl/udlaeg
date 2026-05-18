"""Balance and payment-status computation.

Status is derived on read, never stored:

    total_paid == 0                 -> "pending"
    0 < total_paid < amount         -> "partial"
    total_paid >= amount            -> "paid"   (overpayment still counts as paid)

Per-person saldo = sum(amount - total_paid) over expenses whose status != "paid".
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.expense import Expense
from app.models.payment import Payment
from app.models.person import Person

PENDING = "pending"
PARTIAL = "partial"
PAID = "paid"

ZERO = Decimal("0.00")


def payment_total(payments: Iterable[Payment]) -> Decimal:
    """Sum of payment amounts."""
    total = sum((p.amount_dkk for p in payments), ZERO)
    return Decimal(total).quantize(Decimal("0.01"))


def status_for(amount: Decimal, total_paid: Decimal) -> str:
    """Map (amount, total_paid) to a status string."""
    if total_paid <= ZERO:
        return PENDING
    if total_paid < amount:
        return PARTIAL
    return PAID


def remaining_for(amount: Decimal, total_paid: Decimal) -> Decimal:
    """Outstanding amount for a single expense (clamped at 0)."""
    remaining = amount - total_paid
    return remaining if remaining > ZERO else ZERO


@dataclass(frozen=True)
class ExpenseStatus:
    total_paid: Decimal
    remaining: Decimal
    status: str


def expense_status(expense: Expense) -> ExpenseStatus:
    """Compute status for an expense whose `payments` are loaded."""
    total_paid = payment_total(expense.payments)
    return ExpenseStatus(
        total_paid=total_paid,
        remaining=remaining_for(expense.amount_dkk, total_paid),
        status=status_for(expense.amount_dkk, total_paid),
    )


@dataclass(frozen=True)
class PersonBalance:
    person: Person
    balance: Decimal
    open_count: int


async def person_balances(session: AsyncSession) -> list[PersonBalance]:
    """Outstanding balance per person across all not-fully-paid expenses."""
    result = await session.execute(
        select(Person)
        .options(selectinload(Person.expenses).selectinload(Expense.payments))
        .order_by(Person.name)
    )
    balances: list[PersonBalance] = []
    for person in result.scalars().unique():
        balance = ZERO
        open_count = 0
        for expense in person.expenses:
            st = expense_status(expense)
            if st.status != PAID:
                balance += st.remaining
                open_count += 1
        balances.append(PersonBalance(person=person, balance=balance, open_count=open_count))
    return balances
