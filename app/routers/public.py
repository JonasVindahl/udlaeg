"""Public, unauthenticated per-person status pages.

Reachable only with the person's unguessable share_token under /p/{token}.
Read-only: no actions, no nav. Every nested resource (expense detail,
receipt file) is re-checked to belong to the token's person, so holding
one person's link never exposes another person's data.
"""

import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_async_session
from app.models.expense import Expense
from app.models.person import Person
from app.models.receipt import Receipt
from app.services import balance
from app.services.files import get_receipt_path
from app.templating import templates

logger = logging.getLogger("udlaeg.public")

router = APIRouter(prefix="/p", tags=["public"])

ZERO = Decimal("0.00")


async def _person_by_token(session: AsyncSession, token: str) -> Person | None:
    if not token:
        return None
    result = await session.execute(select(Person).where(Person.share_token == token))
    return result.scalars().first()


def _invalid(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "public/invalid.html", {}, status_code=404)


@router.get("/{token}", response_class=HTMLResponse)
async def public_status(
    request: Request,
    token: str,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    result = await session.execute(
        select(Person)
        .where(Person.share_token == token)
        .options(
            selectinload(Person.expenses).selectinload(Expense.payments),
            selectinload(Person.expenses).selectinload(Expense.receipts),
        )
    )
    person = result.scalars().first()
    if person is None or not token:
        logger.info("public.status.invalid_token")
        return _invalid(request)

    expenses = sorted(person.expenses, key=lambda e: (e.date, e.id), reverse=True)
    rows = [(e, balance.expense_status(e)) for e in expenses]
    open_rows = [(e, st) for e, st in rows if st.status != balance.PAID]
    paid_rows = [(e, st) for e, st in rows if st.status == balance.PAID]
    outstanding = sum((st.remaining for _, st in open_rows), ZERO)

    logger.info("public.status.view", extra={"person_id": person.id})
    return templates.TemplateResponse(
        request,
        "public/status.html",
        {
            "token": token,
            "person": person,
            "open_rows": open_rows,
            "paid_rows": paid_rows,
            "outstanding": outstanding,
        },
    )


@router.get("/{token}/expense/{expense_id}", response_class=HTMLResponse)
async def public_expense(
    request: Request,
    token: str,
    expense_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    person = await _person_by_token(session, token)
    if person is None:
        return _invalid(request)

    result = await session.execute(
        select(Expense)
        .where(Expense.id == expense_id, Expense.person_id == person.id)
        .options(selectinload(Expense.payments), selectinload(Expense.receipts))
    )
    expense = result.scalars().first()
    if expense is None:
        return _invalid(request)

    st = balance.expense_status(expense)
    receipts = sorted(expense.receipts, key=lambda r: r.id)
    logger.info(
        "public.expense.view", extra={"person_id": person.id, "expense_id": expense_id}
    )
    return templates.TemplateResponse(
        request,
        "public/expense.html",
        {"token": token, "person": person, "expense": expense, "st": st, "receipts": receipts},
    )


@router.get("/{token}/receipt/{receipt_id}")
async def public_receipt_file(
    token: str,
    receipt_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> FileResponse:
    person = await _person_by_token(session, token)
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    receipt = await session.get(Receipt, receipt_id)
    if receipt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    expense = await session.get(Expense, receipt.expense_id)
    if expense is None or expense.person_id != person.id:
        # The receipt exists but is not this person's — treat as not found.
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    path = get_receipt_path(receipt)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filen findes ikke på disk")
    return FileResponse(path, media_type=receipt.mime_type, filename=path.name)
