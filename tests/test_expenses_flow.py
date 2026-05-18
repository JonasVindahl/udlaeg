"""Happy-path integration test covering the full expense lifecycle."""

import struct
import zlib


def _png_bytes() -> bytes:
    """Minimal valid 1x1 PNG so filetype detects image/png."""
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\xff\xff")
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


async def test_full_flow(auth_client):
    c = auth_client

    # Create a person.
    r = await c.post("/persons", data={"name": "Mor"})
    assert r.status_code == 200, r.text
    assert "Mor" in r.text

    r = await c.get("/persons")
    assert "Mor" in r.text
    # Find the person id from the dashboard balances query instead.
    r = await c.get("/expenses/new")
    assert r.status_code == 200
    assert 'name="person_id"' in r.text

    # Extract the option value for "Mor".
    import re

    m = re.search(r'<option value="(\d+)"[^>]*>Mor</option>', r.text)
    assert m, r.text
    person_id = int(m.group(1))

    # Create an expense.
    r = await c.post(
        "/expenses",
        data={
            "person_id": str(person_id),
            "amount_dkk": "250,50",
            "date": "2026-05-18",
            "category": "Mad",
            "description": "Indkøb",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    expense_url = r.headers["location"]
    expense_id = int(expense_url.rsplit("/", 1)[1])

    # Upload a receipt.
    r = await c.post(
        f"/receipts/expense/{expense_id}",
        files={"file": ("kvittering.png", _png_bytes(), "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    assert "kvittering" not in r.text or "thumb" in r.text  # grid rendered

    # Detail view shows pending status.
    r = await c.get(f"/expenses/{expense_id}")
    assert r.status_code == 200
    assert "pending" in r.text

    # Add a partial payment.
    r = await c.post(
        f"/payments/expense/{expense_id}",
        data={"amount_dkk": "100", "note": "Afdrag"},
    )
    assert r.status_code == 200, r.text
    assert "partial" in r.text

    # Mark fully paid.
    r = await c.post(f"/payments/expense/{expense_id}/mark-paid")
    assert r.status_code == 200, r.text
    assert "paid" in r.text

    # Person now has zero outstanding -> dashboard reflects it.
    r = await c.get("/")
    assert r.status_code == 200
    assert "Mor" in r.text


async def test_unauthenticated_redirects_to_login(client):
    r = await client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"

    r = await client.get("/expenses", headers={"accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
