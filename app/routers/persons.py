"""Person CRUD (HTMX-driven list + inline forms)."""

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.models.person import Person, new_share_token
from app.templating import templates
from app.users import current_active_user

logger = logging.getLogger("udlaeg.persons")

router = APIRouter(prefix="/persons", tags=["persons"], dependencies=[Depends(current_active_user)])


async def _all_persons(session: AsyncSession) -> list[Person]:
    result = await session.execute(select(Person).order_by(Person.name))
    return list(result.scalars().all())


@router.get("", response_class=HTMLResponse)
async def list_persons(
    request: Request, session: AsyncSession = Depends(get_async_session)
) -> HTMLResponse:
    persons = await _all_persons(session)
    return templates.TemplateResponse(request, "persons/list.html", {"persons": persons})


@router.post("", response_class=HTMLResponse)
async def create_person(
    request: Request,
    name: str = Form(...),
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    name = name.strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Navn må ikke være tomt")
    person = Person(name=name)
    session.add(person)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "En person med det navn findes allerede"
        ) from None
    logger.info("person.create", extra={"person_name": name})
    persons = await _all_persons(session)
    return templates.TemplateResponse(request, "partials/person_rows.html", {"persons": persons})


@router.get("/{person_id}/edit", response_class=HTMLResponse)
async def edit_person_form(
    request: Request,
    person_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    person = await session.get(Person, person_id)
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return templates.TemplateResponse(request, "partials/person_edit_row.html", {"person": person})


@router.post("/{person_id}", response_class=HTMLResponse)
async def update_person(
    request: Request,
    person_id: int,
    name: str = Form(...),
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    person = await session.get(Person, person_id)
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    person.name = name.strip()
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Navnet er allerede i brug") from None
    logger.info("person.update", extra={"person_id": person_id})
    persons = await _all_persons(session)
    return templates.TemplateResponse(request, "partials/person_rows.html", {"persons": persons})


async def _set_share_token(
    request: Request,
    person_id: int,
    token: str | None,
    session: AsyncSession,
    *,
    log_event: str,
) -> HTMLResponse:
    person = await session.get(Person, person_id)
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    person.share_token = token
    await session.commit()
    logger.info(log_event, extra={"person_id": person_id})
    persons = await _all_persons(session)
    return templates.TemplateResponse(request, "partials/person_rows.html", {"persons": persons})


@router.post("/{person_id}/share/regenerate", response_class=HTMLResponse)
async def regenerate_share(
    request: Request,
    person_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    return await _set_share_token(
        request, person_id, new_share_token(), session, log_event="person.share.regenerate"
    )


@router.post("/{person_id}/share/enable", response_class=HTMLResponse)
async def enable_share(
    request: Request,
    person_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    return await _set_share_token(
        request, person_id, new_share_token(), session, log_event="person.share.enable"
    )


@router.post("/{person_id}/share/revoke", response_class=HTMLResponse)
async def revoke_share(
    request: Request,
    person_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    return await _set_share_token(
        request, person_id, None, session, log_event="person.share.revoke"
    )


@router.post("/{person_id}/delete", response_class=HTMLResponse)
async def delete_person(
    request: Request,
    person_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    person = await session.get(Person, person_id)
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await session.delete(person)
    await session.commit()
    logger.info("person.delete", extra={"person_id": person_id})
    persons = await _all_persons(session)
    return templates.TemplateResponse(request, "partials/person_rows.html", {"persons": persons})
