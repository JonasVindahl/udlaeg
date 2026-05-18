"""Login / logout. No public registration is exposed."""

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import get_settings
from app.templating import templates
from app.users import (
    COOKIE_LIFETIME_SECONDS,
    UserManager,
    get_jwt_strategy,
    get_user_manager,
)

settings = get_settings()

logger = logging.getLogger("udlaeg.auth")

router = APIRouter(tags=["auth"])

COOKIE_NAME = "udlaeg_session"


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_model=None)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    user_manager: UserManager = Depends(get_user_manager),
) -> HTMLResponse | RedirectResponse:
    from fastapi.security import OAuth2PasswordRequestForm

    credentials = OAuth2PasswordRequestForm(username=email, password=password)
    user = await user_manager.authenticate(credentials)
    if user is None or not user.is_active:
        logger.warning("auth.login.fail", extra={"user_email": email})
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Forkert email eller adgangskode"},
            status_code=401,
        )

    strategy = get_jwt_strategy()
    token = await strategy.write_token(user)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_LIFETIME_SECONDS,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    logger.info("auth.login.success", extra={"user_email": user.email})
    return response


@router.get("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key=COOKIE_NAME)
    return response
