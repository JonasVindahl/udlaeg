"""Receipt upload, streaming download and delete."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models.expense import Expense
from app.models.receipt import Receipt
from app.services.files import delete_receipt, get_receipt_path, save_receipt
from app.templating import templates
from app.users import current_active_user

logger = logging.getLogger("udlaeg.receipts")

router = APIRouter(
    prefix="/receipts", tags=["receipts"], dependencies=[Depends(current_active_user)]
)


@router.get("/{receipt_id}/file")
async def receipt_file(
    receipt_id: int, session: AsyncSession = Depends(get_async_session)
) -> FileResponse:
    receipt = await session.get(Receipt, receipt_id)
    if receipt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    path = get_receipt_path(receipt)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filen findes ikke på disk")
    return FileResponse(path, media_type=receipt.mime_type, filename=path.name)


@router.post("/expense/{expense_id}", response_class=HTMLResponse)
async def upload_receipt(
    request: Request,
    expense_id: int,
    file: UploadFile,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    expense = await session.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await save_receipt(session, expense_id, file)
    await session.refresh(expense, attribute_names=["receipts"])
    return templates.TemplateResponse(request, "partials/receipt_grid.html", {"expense": expense})


@router.post("/{receipt_id}/delete", response_class=HTMLResponse)
async def remove_receipt(
    request: Request,
    receipt_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    receipt = await session.get(Receipt, receipt_id)
    if receipt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    expense_id = receipt.expense_id
    await delete_receipt(session, receipt)
    expense = await session.get(Expense, expense_id)
    await session.refresh(expense, attribute_names=["receipts"])
    return templates.TemplateResponse(request, "partials/receipt_grid.html", {"expense": expense})
