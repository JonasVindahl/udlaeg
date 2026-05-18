"""Public expense-detail page + token-scoped receipt streaming.

Core property under test: holding person A's share link must never expose
person B's expense or receipt, even by guessing numeric ids.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.config import get_settings
from app.models.expense import Expense
from app.models.payment import Payment
from app.models.person import Person
from app.models.receipt import Receipt

pytestmark = pytest.mark.asyncio

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-receipt-image-data"


async def _person_with_receipt(db_session, name: str, desc: str) -> tuple[Person, Expense, Receipt]:
    person = Person(name=name)
    db_session.add(person)
    await db_session.flush()

    expense = Expense(
        person_id=person.id,
        amount_dkk=Decimal("200.00"),
        currency="DKK",
        date=date(2026, 5, 1),
        category="Transport",
        description=desc,
    )
    db_session.add(expense)
    await db_session.flush()
    db_session.add(Payment(expense_id=expense.id, amount_dkk=Decimal("50.00")))

    settings = get_settings()
    rdir = settings.receipts_dir / str(expense.id)
    rdir.mkdir(parents=True, exist_ok=True)
    fpath = rdir / "receipt.png"
    fpath.write_bytes(PNG_BYTES)
    receipt = Receipt(
        expense_id=expense.id,
        file_path=str(fpath),
        mime_type="image/png",
        file_size=len(PNG_BYTES),
    )
    db_session.add(receipt)
    await db_session.commit()
    await db_session.refresh(person)
    await db_session.refresh(expense)
    await db_session.refresh(receipt)
    return person, expense, receipt


async def test_detail_page_shows_full_description_and_receipt(client, db_session):
    long_desc = "Togbillet København–Aarhus tur/retur for hele familien"
    person, expense, receipt = await _person_with_receipt(db_session, "Mor", long_desc)

    resp = await client.get(f"/p/{person.share_token}/expense/{expense.id}")
    assert resp.status_code == 200
    assert long_desc in resp.text
    assert "Transport" in resp.text
    assert f"/p/{person.share_token}/receipt/{receipt.id}" in resp.text


async def test_status_page_links_to_detail(client, db_session):
    person, expense, _ = await _person_with_receipt(db_session, "Mor", "Indkøb")
    resp = await client.get(f"/p/{person.share_token}")
    assert resp.status_code == 200
    assert f"/p/{person.share_token}/expense/{expense.id}" in resp.text


async def test_receipt_streams_without_auth(client, db_session):
    person, _, receipt = await _person_with_receipt(db_session, "Mor", "Bus")
    resp = await client.get(f"/p/{person.share_token}/receipt/{receipt.id}")
    assert resp.status_code == 200
    assert resp.content == PNG_BYTES
    assert resp.headers["content-type"] == "image/png"


async def test_cannot_open_other_persons_expense_with_my_token(client, db_session):
    a, _, _ = await _person_with_receipt(db_session, "Mor", "A's udlæg")
    _, exp_b, _ = await _person_with_receipt(db_session, "Far", "B's udlæg")

    resp = await client.get(f"/p/{a.share_token}/expense/{exp_b.id}")
    assert resp.status_code == 404
    assert "B's udlæg" not in resp.text


async def test_cannot_fetch_other_persons_receipt_with_my_token(client, db_session):
    a, _, _ = await _person_with_receipt(db_session, "Mor", "A")
    _, _, rcpt_b = await _person_with_receipt(db_session, "Far", "B")

    resp = await client.get(f"/p/{a.share_token}/receipt/{rcpt_b.id}")
    assert resp.status_code == 404
    assert resp.content != PNG_BYTES


async def test_detail_and_receipt_reject_bad_token(client, db_session):
    _, expense, receipt = await _person_with_receipt(db_session, "Mor", "X")
    assert (await client.get(f"/p/nope/expense/{expense.id}")).status_code == 404
    assert (await client.get(f"/p/nope/receipt/{receipt.id}")).status_code == 404


async def test_revoked_token_blocks_receipt(auth_client, db_session):
    person, _, receipt = await _person_with_receipt(db_session, "Mor", "Y")
    token = person.share_token
    await auth_client.post(f"/persons/{person.id}/share/revoke")
    assert (await auth_client.get(f"/p/{token}/receipt/{receipt.id}")).status_code == 404
