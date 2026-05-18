"""Dashboard: per-person balance overview + latest expenses."""

from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_async_session
from app.models.expense import Expense
from app.models.user import User
from app.services import balance
from app.templating import templates
from app.users import optional_current_user

router = APIRouter(tags=["dashboard"])


@router.get("/", response_class=HTMLResponse, response_model=None)
async def dashboard(
    request: Request,
    user: User | None = Depends(optional_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse | RedirectResponse:
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    balances = await balance.person_balances(session)
    result = await session.execute(
        select(Expense)
        .options(selectinload(Expense.payments), selectinload(Expense.person))
        .order_by(Expense.created_at.desc(), Expense.id.desc())
        .limit(10)
    )
    latest = [(e, balance.expense_status(e)) for e in result.scalars().unique()]
    total_outstanding = sum((b.balance for b in balances), Decimal("0.00"))
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"balances": balances, "latest": latest, "total_outstanding": total_outstanding},
    )
