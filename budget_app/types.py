"""Shared value types and DTOs that are not JSONL-persisted entities.

``models`` holds :class:`~budget_app.models.Transaction` and the other
records with ``to_dict`` / ``from_dict``. This module holds ephemeral shapes
used across CLI, CSV, and services: search criteria, monthly aggregates, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class TransactionFilters:
    """Search criteria for :func:`budget_app.services.search_transactions`."""

    from_date: date | None = None
    to_date: date | None = None
    category: str | None = None
    type: str | None = None
    query: str | None = None
    tag: str | None = None


@dataclass(frozen=True)
class CategoryAmount:
    """A single (category, amount) pair used for top-N reports."""

    category: str
    amount: int


@dataclass(frozen=True)
class BudgetUsage:
    """How much of a monthly budget has been consumed (plan.md §9.3)."""

    limit: int
    used: int
    ratio: float
    over_amount: int

    @property
    def is_over(self) -> bool:
        """Return ``True`` if ``used`` exceeds ``limit``."""
        return self.over_amount > 0


@dataclass(frozen=True)
class MonthlySummary:
    """Summary numbers for a single ``YYYY-MM`` month."""

    year_month: str
    income: int
    expense: int
    balance: int
    top_categories: list[CategoryAmount] = field(default_factory=list)
    budget_usage: BudgetUsage | None = None

    @property
    def is_empty(self) -> bool:
        """Return ``True`` when the month has no transactions."""
        return self.income == 0 and self.expense == 0 and not self.top_categories


__all__ = [
    "BudgetUsage",
    "CategoryAmount",
    "MonthlySummary",
    "TransactionFilters",
]
