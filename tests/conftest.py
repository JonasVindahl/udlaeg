"""Test fixtures: in-memory SQLite, tmp data dir, authenticated client."""

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db import Base, get_async_session
from app.main import app
from app.models.user import User  # noqa: F401  (register table)
from app.users import get_user_db, get_user_manager

TEST_EMAIL = "owner@example.com"
TEST_PASSWORD = "s3cret-password"


@pytest_asyncio.fixture
async def session_maker(tmp_path):
    # Point all file storage at a throwaway tmp dir.
    settings = get_settings()
    settings.data_dir = tmp_path
    settings.session_cookie_secure = False  # test client speaks http
    (tmp_path / "receipts").mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield maker
    await engine.dispose()


@pytest_asyncio.fixture
async def client(session_maker) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_maker() as s:
            yield s

    app.dependency_overrides[get_async_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def db_session(session_maker) -> AsyncGenerator[AsyncSession, None]:
    async with session_maker() as s:
        yield s


@pytest_asyncio.fixture
async def auth_client(client, session_maker) -> AsyncClient:
    """A client logged in as a seeded superuser."""
    async with session_maker() as session:
        user_db_gen = get_user_db(session)
        user_db = await user_db_gen.__anext__()
        manager_gen = get_user_manager(user_db)
        manager = await manager_gen.__anext__()
        from app.schemas.user import UserCreate

        await manager.create(
            UserCreate(
                email=TEST_EMAIL,
                password=TEST_PASSWORD,
                is_active=True,
                is_superuser=True,
            )
        )

    resp = await client.post(
        "/login",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
    return client


def make_payment(amount: str):
    """Lightweight Payment-like stub for pure balance unit tests."""
    from decimal import Decimal

    class _P:
        def __init__(self, a):
            self.amount_dkk = Decimal(a)

    return _P(amount)


def make_expense(amount: str, payments):
    from decimal import Decimal

    class _E:
        def __init__(self):
            self.amount_dkk = Decimal(amount)
            self.payments = payments

    return _E()


@pytest.fixture
def uid() -> str:
    return uuid.uuid4().hex
