"""Payment add / delete / mark-fully-paid (HTMX panel updates)."""

import logging
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_async_session
from app.models.expense import Expense
from app.models.payment import Payment
from app.services import balance
from app.templating import templates
from app.users import current_active_user

logger = logging.getLogger("udlaeg.payments")

router = APIRouter(
    prefix="/payments", tags=["payments"], dependencies=[Depends(current_active_user)]
)


async def _load_expense(session: AsyncSession, expense_id: int) -> Expense:
    result = await session.execute(
        select(Expense)
        .where(Expense.id == expense_id)
        .options(selectinload(Expense.payments))
        .execution_options(populate_existing=True)
    )
    expense = result.scalar_one_or_none()
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return expense


def _panel(request: Request, expense: Expense) -> HTMLResponse:
    st = balance.expense_status(expense)
    return templates.TemplateResponse(
        request, "partials/payment_panel.html", {"expense": expense, "st": st}
    )


@router.post("/expense/{expense_id}", response_class=HTMLResponse)
async def add_payment(
    request: Request,
    expense_id: int,
    amount_dkk: str = Form(...),
    note: str | None = Form(None),
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    expense = await _load_expense(session, expense_id)
    try:
        amount = Decimal(amount_dkk.replace(",", ".").strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, AttributeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ugyldigt beløb") from None
    if amount <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Beløb skal være positivt")
    session.add(Payment(expense_id=expense_id, amount_dkk=amount, note=note or None))
    await session.commit()
    logger.info("payment.add", extra={"expense_id": expense_id, "amount": str(amount)})
    expense = await _load_expense(session, expense_id)
    return _panel(request, expense)


@router.post("/{payment_id}/delete", response_class=HTMLResponse)
async def delete_payment(
    request: Request,
    payment_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    expense_id = payment.expense_id
    await session.delete(payment)
    await session.commit()
    logger.info("payment.delete", extra={"payment_id": payment_id})
    expense = await _load_expense(session, expense_id)
    return _panel(request, expense)


@router.post("/expense/{expense_id}/mark-paid", response_class=HTMLResponse)
async def mark_fully_paid(
    request: Request,
    expense_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    expense = await _load_expense(session, expense_id)
    st = balance.expense_status(expense)
    if st.remaining > 0:
        session.add(
            Payment(
                expense_id=expense_id,
                amount_dkk=st.remaining,
                note="Markeret fuldt betalt",
            )
        )
        await session.commit()
        logger.info("payment.mark_paid", extra={"expense_id": expense_id})
        expense = await _load_expense(session, expense_id)
    return _panel(request, expense)
