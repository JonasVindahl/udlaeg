"""Jinja2 environment plus Danish locale formatting filters."""

from datetime import date, datetime
from decimal import Decimal

from babel.dates import format_date
from fastapi.templating import Jinja2Templates


def format_kr(value: Decimal | float | int | None) -> str:
    """Format an amount as Danish currency, e.g. '1.234,56 kr'."""
    if value is None:
        value = 0
    amount = Decimal(value).quantize(Decimal("0.01"))
    sign = "-" if amount < 0 else ""
    integer, frac = f"{abs(amount):.2f}".split(".")
    grouped = ""
    while len(integer) > 3:
        grouped = "." + integer[-3:] + grouped
        integer = integer[:-3]
    grouped = integer + grouped
    return f"{sign}{grouped},{frac} kr"


def format_dk_date(value: date | datetime | None) -> str:
    """Format a date as e.g. '18. maj 2026'."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = value.date()
    return format_date(value, format="d. MMMM y", locale="da")


templates = Jinja2Templates(directory="app/templates")
templates.env.filters["kr"] = format_kr
templates.env.filters["dkdate"] = format_dk_date
