"""Public, unauthenticated per-person status page.

Reachable only with the person's unguessable share_token at /p/{token}.
Read-only: no actions, no nav, nothing sensitive beyond the person's own
outstanding expenses.
"""

import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_async_session
from app.models.expense import Expense
from app.models.person import Person
from app.services import balance
from app.templating import templates

logger = logging.getLogger("udlaeg.public")

router = APIRouter(tags=["public"])

ZERO = Decimal("0.00")


@router.get("/p/{token}", response_class=HTMLResponse)
async def public_status(
    request: Request,
    token: str,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    result = await session.execute(
        select(Person)
        .where(Person.share_token == token)
        .options(selectinload(Person.expenses).selectinload(Expense.payments))
    )
    person = result.scalars().first()

    if person is None or not token:
        logger.info("public.status.invalid_token")
        return templates.TemplateResponse(
            request, "public/invalid.html", {}, status_code=404
        )

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
            "person": person,
            "open_rows": open_rows,
            "paid_rows": paid_rows,
            "outstanding": outstanding,
        },
    )
