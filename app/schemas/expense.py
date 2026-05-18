"""Pydantic schemas for persons, expenses and payments."""

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PersonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class PersonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


class ExpenseCreate(BaseModel):
    person_id: int
    amount_dkk: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    currency: str = "DKK"
    date: date_type
    category: str | None = None
    description: str | None = None


class ExpenseUpdate(BaseModel):
    person_id: int
    amount_dkk: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    currency: str = "DKK"
    date: date_type
    category: str | None = None
    description: str | None = None


class PaymentCreate(BaseModel):
    amount_dkk: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    note: str | None = None
