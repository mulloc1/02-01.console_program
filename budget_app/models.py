"""Domain dataclasses for budget_app.

Defines the three persisted entities (`Transaction`, `Category`, `Budget`)
with explicit ``to_dict()`` / ``from_dict()`` serialisers. Heavy input
validation belongs to ``utils`` / ``services``; non-persisted DTOs such as
search filters and monthly summaries live in :mod:`budget_app.types`. This
module only enforces the contract needed for round-tripping JSONL records
(plan.md §4, §5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


TRANSACTION_TYPES: tuple[str, ...] = ("income", "expense")


@dataclass(frozen=True)
class Transaction:
    """A single income or expense entry."""

    id: str
    type: str
    date: date
    amount: int
    category: str
    memo: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "id": self.id,
            "type": self.type,
            "date": self.date.isoformat(),
            "amount": self.amount,
            "category": self.category,
            "memo": self.memo,
            "tags": list(self.tags),
        }

    def from_dict(payload: dict[str, Any]) -> "Transaction":
        """Build a ``Transaction`` from its ``to_dict`` representation."""
        type_value = payload["type"]
        if type_value not in TRANSACTION_TYPES:
            raise ValueError(f"invalid transaction type: {type_value!r}")
        return Transaction(
            id=str(payload["id"]),
            type=type_value,
            date=date.fromisoformat(payload["date"]),
            amount=int(payload["amount"]),
            category=str(payload["category"]),
            memo=str(payload.get("memo", "")),
            tags=list(payload.get("tags") or []),
        )


@dataclass(frozen=True)
class Category:
    """A user-defined transaction category (plan.md §4)."""

    name: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {"name": self.name}

    def from_dict(payload: dict[str, Any]) -> "Category":
        """Build a ``Category`` from its ``to_dict`` representation."""
        return Category(name=str(payload["name"]))


@dataclass(frozen=True)
class Budget:
    """A monthly spending limit keyed by ``year_month`` (`YYYY-MM`, plan.md §4)."""

    year_month: str
    amount: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {"year_month": self.year_month, "amount": self.amount}

    def from_dict(payload: dict[str, Any]) -> "Budget":
        """Build a ``Budget`` from its ``to_dict`` representation."""
        year_month = payload.get("year_month", payload.get("month"))
        if year_month is None:
            raise KeyError("missing key: year_month")
        return Budget(year_month=str(year_month), amount=int(payload["amount"]))
