"""Import all models so Base.metadata is fully populated."""

from app.models.expense import Expense
from app.models.payment import Payment
from app.models.person import Person
from app.models.receipt import Receipt
from app.models.user import User

__all__ = ["Expense", "Payment", "Person", "Receipt", "User"]
