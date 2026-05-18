"""Per-person public share link: token lifecycle + unauthenticated view."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.expense import Expense
from app.models.payment import Payment
from app.models.person import Person

pytestmark = pytest.mark.asyncio


async def _seed(db_session) -> Person:
    person = Person(name="Mor")
    db_session.add(person)
    await db_session.flush()
    expense = Expense(
        person_id=person.id,
        amount_dkk=Decimal("200.00"),
        currency="DKK",
        date=date(2026, 5, 1),
        description="Togbillet",
    )
    db_session.add(expense)
    await db_session.flush()
    db_session.add(Payment(expense_id=expense.id, amount_dkk=Decimal("50.00")))
    await db_session.commit()
    await db_session.refresh(person)
    return person


async def test_person_gets_token_on_create(db_session):
    person = await _seed(db_session)
    assert person.share_token
    assert len(person.share_token) >= 20


async def test_public_page_needs_no_auth_and_shows_outstanding(client, db_session):
    person = await _seed(db_session)
    resp = await client.get(f"/p/{person.share_token}")
    assert resp.status_code == 200
    assert "Mor" in resp.text
    assert "150,00 kr" in resp.text  # 200 owed - 50 paid
    # nav must not leak onto the public page
    assert 'class="topbar"' not in resp.text


async def test_unknown_token_returns_404(client):
    resp = await client.get("/p/this-token-does-not-exist")
    assert resp.status_code == 404
    assert "virker ikke" in resp.text


async def test_revoke_invalidates_link(auth_client, db_session):
    person = await _seed(db_session)
    token = person.share_token

    revoked = await auth_client.post(f"/persons/{person.id}/share/revoke")
    assert revoked.status_code == 200

    assert (await auth_client.get(f"/p/{token}")).status_code == 404


async def test_regenerate_rotates_token(auth_client, db_session):
    person = await _seed(db_session)
    old = person.share_token

    resp = await auth_client.post(f"/persons/{person.id}/share/regenerate")
    assert resp.status_code == 200

    await db_session.refresh(person)
    assert person.share_token and person.share_token != old
    assert (await auth_client.get(f"/p/{old}")).status_code == 404
    assert (await auth_client.get(f"/p/{person.share_token}")).status_code == 200


async def test_enable_after_revoke(auth_client, db_session):
    person = await _seed(db_session)
    await auth_client.post(f"/persons/{person.id}/share/revoke")

    resp = await auth_client.post(f"/persons/{person.id}/share/enable")
    assert resp.status_code == 200

    await db_session.refresh(person)
    assert person.share_token
    assert (await auth_client.get(f"/p/{person.share_token}")).status_code == 200


async def test_persons_list_shows_share_link(auth_client, db_session):
    person = await _seed(db_session)
    resp = await auth_client.get("/persons")
    assert resp.status_code == 200
    assert f"/p/{person.share_token}" in resp.text
