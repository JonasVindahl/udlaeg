"""Expense list (filterable), create/edit, and detail views."""

import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_async_session
from app.models.expense import Expense
from app.models.person import Person
from app.services import balance
from app.services.files import save_receipt
from app.templating import templates
from app.users import current_active_user

logger = logging.getLogger("udlaeg.expenses")

router = APIRouter(
    prefix="/expenses", tags=["expenses"], dependencies=[Depends(current_active_user)]
)

PAGE_SIZE = 50


def _parse_amount(raw: str) -> Decimal:
    try:
        amount = Decimal(raw.replace(",", ".").strip())
    except (InvalidOperation, AttributeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ugyldigt beløb") from None
    if amount <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Beløb skal være positivt")
    return amount.quantize(Decimal("0.01"))


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ugyldig dato") from None


@router.get("", response_class=HTMLResponse)
async def list_expenses(
    request: Request,
    person_id: int | None = None,
    expense_status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    stmt = (
        select(Expense)
        .options(selectinload(Expense.payments), selectinload(Expense.person))
        .order_by(Expense.date.desc(), Expense.id.desc())
    )
    if person_id:
        stmt = stmt.where(Expense.person_id == person_id)
    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    if df:
        stmt = stmt.where(Expense.date >= df)
    if dt:
        stmt = stmt.where(Expense.date <= dt)

    result = await session.execute(stmt)
    rows = []
    for exp in result.scalars().unique():
        st = balance.expense_status(exp)
        if expense_status and st.status != expense_status:
            continue
        rows.append((exp, st))

    total = len(rows)
    page = max(page, 1)
    start = (page - 1) * PAGE_SIZE
    page_rows = rows[start : start + PAGE_SIZE]
    has_next = total > start + PAGE_SIZE

    persons = (await session.execute(select(Person).order_by(Person.name))).scalars().all()
    ctx = {
        "rows": page_rows,
        "persons": persons,
        "filters": {
            "person_id": person_id,
            "expense_status": expense_status,
            "date_from": date_from,
            "date_to": date_to,
        },
        "page": page,
        "has_next": has_next,
        "total": total,
    }
    is_htmx = request.headers.get("HX-Request")
    template = "partials/expense_rows.html" if is_htmx else "expenses/list.html"
    return templates.TemplateResponse(request, template, ctx)


@router.get("/new", response_class=HTMLResponse)
async def new_expense_form(
    request: Request, session: AsyncSession = Depends(get_async_session)
) -> HTMLResponse:
    persons = (await session.execute(select(Person).order_by(Person.name))).scalars().all()
    return templates.TemplateResponse(
        request, "expenses/form.html", {"persons": persons, "expense": None}
    )


@router.post("")
async def create_expense(
    person_id: int = Form(...),
    amount_dkk: str = Form(...),
    date_value: str = Form(..., alias="date"),
    currency: str = Form("DKK"),
    category: str | None = Form(None),
    description: str | None = Form(None),
    receipt: UploadFile | None = None,
    session: AsyncSession = Depends(get_async_session),
) -> RedirectResponse:
    if await session.get(Person, person_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ukendt person")
    expense = Expense(
        person_id=person_id,
        amount_dkk=_parse_amount(amount_dkk),
        currency=(currency or "DKK").upper()[:3],
        date=_parse_date(date_value) or date.today(),
        category=(category or None),
        description=(description or None),
    )
    session.add(expense)
    await session.commit()
    await session.refresh(expense)
    logger.info("expense.create", extra={"expense_id": expense.id})
    if receipt is not None and receipt.filename:
        await save_receipt(session, expense.id, receipt)
    return RedirectResponse(url=f"/expenses/{expense.id}", status_code=303)


@router.get("/{expense_id}", response_class=HTMLResponse)
async def expense_detail(
    request: Request,
    expense_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    result = await session.execute(
        select(Expense)
        .where(Expense.id == expense_id)
        .options(
            selectinload(Expense.payments),
            selectinload(Expense.receipts),
            selectinload(Expense.person),
        )
    )
    expense = result.scalar_one_or_none()
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    st = balance.expense_status(expense)
    return templates.TemplateResponse(
        request, "expenses/detail.html", {"expense": expense, "st": st}
    )


@router.get("/{expense_id}/edit", response_class=HTMLResponse)
async def edit_expense_form(
    request: Request,
    expense_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    expense = await session.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    persons = (await session.execute(select(Person).order_by(Person.name))).scalars().all()
    return templates.TemplateResponse(
        request, "expenses/form.html", {"persons": persons, "expense": expense}
    )


@router.post("/{expense_id}")
async def update_expense(
    expense_id: int,
    person_id: int = Form(...),
    amount_dkk: str = Form(...),
    date_value: str = Form(..., alias="date"),
    currency: str = Form("DKK"),
    category: str | None = Form(None),
    description: str | None = Form(None),
    receipt: UploadFile | None = None,
    session: AsyncSession = Depends(get_async_session),
) -> RedirectResponse:
    expense = await session.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    expense.person_id = person_id
    expense.amount_dkk = _parse_amount(amount_dkk)
    expense.currency = (currency or "DKK").upper()[:3]
    expense.date = _parse_date(date_value) or expense.date
    expense.category = category or None
    expense.description = description or None
    await session.commit()
    logger.info("expense.update", extra={"expense_id": expense_id})
    if receipt is not None and receipt.filename:
        await save_receipt(session, expense_id, receipt)
    return RedirectResponse(url=f"/expenses/{expense_id}", status_code=303)


@router.post("/{expense_id}/delete")
async def delete_expense(
    expense_id: int, session: AsyncSession = Depends(get_async_session)
) -> RedirectResponse:
    expense = await session.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await session.delete(expense)
    await session.commit()
    logger.info("expense.delete", extra={"expense_id": expense_id})
    return RedirectResponse(url="/expenses", status_code=303)
