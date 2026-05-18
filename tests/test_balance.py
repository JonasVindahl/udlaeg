"""Unit tests for status / saldo computation."""

from decimal import Decimal

from app.services import balance
from tests.conftest import make_expense, make_payment


def test_status_pending_no_payments():
    exp = make_expense("100.00", [])
    st = balance.expense_status(exp)
    assert st.status == balance.PENDING
    assert st.total_paid == Decimal("0.00")
    assert st.remaining == Decimal("100.00")


def test_status_partial():
    exp = make_expense("100.00", [make_payment("40.00")])
    st = balance.expense_status(exp)
    assert st.status == balance.PARTIAL
    assert st.total_paid == Decimal("40.00")
    assert st.remaining == Decimal("60.00")


def test_status_paid_exact():
    exp = make_expense("100.00", [make_payment("60.00"), make_payment("40.00")])
    st = balance.expense_status(exp)
    assert st.status == balance.PAID
    assert st.remaining == Decimal("0.00")


def test_status_overpayment_is_paid_and_clamped():
    exp = make_expense("100.00", [make_payment("150.00")])
    st = balance.expense_status(exp)
    assert st.status == balance.PAID
    assert st.total_paid == Decimal("150.00")
    assert st.remaining == Decimal("0.00")


def test_status_for_boundaries():
    assert balance.status_for(Decimal("100"), Decimal("0")) == balance.PENDING
    assert balance.status_for(Decimal("100"), Decimal("99.99")) == balance.PARTIAL
    assert balance.status_for(Decimal("100"), Decimal("100")) == balance.PAID
    assert balance.status_for(Decimal("100"), Decimal("100.01")) == balance.PAID
