"""Business logic for budget_app (plan.md §6, §11).

Services are pure orchestration: they receive repositories from
``budget_app.repositories`` as parameters, validate the input, and either
yield/return domain objects or raise :mod:`budget_app.errors`. I/O lives
inside the repositories so tests can swap in temporary directories
(.cursorrules §4 SRP).

CSV import/export is intentionally deferred to Phase 2.5.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Iterator, Sequence

from budget_app.errors import (
    BudgetAppError,
    CategoryInUseError,
    NotFoundError,
    UserInputError,
)
from budget_app.models import (
    TRANSACTION_TYPES,
    Budget,
    Category,
    Transaction,
)
from budget_app.repositories import (
    BudgetRepository,
    CategoryRepository,
    TransactionRepository,
)


DEFAULT_CATEGORIES: tuple[str, ...] = ("food", "transport", "rent", "etc")
_YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _default_id_factory() -> str:
    return uuid.uuid4().hex[:12]


@dataclass(frozen=True)
class TransactionFilters:
    """Search criteria for ``search_transactions`` (plan.md §6, subject §4.9)."""

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


def _parse_iso_date(value: str, *, field_name: str = "date") -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise UserInputError(
            f"{field_name} 는 YYYY-MM-DD 형식이어야 합니다.", value=value
        )


def _parse_positive_int(value: object, *, field_name: str) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise UserInputError(f"{field_name} 는 정수여야 합니다.", value=value)
    if parsed <= 0:
        raise UserInputError(
            f"{field_name} 는 양수여야 합니다.",
            value=parsed,
            hint="0 보다 큰 정수를 입력하세요.",
        )
    return parsed


def _validate_year_month(value: str) -> None:
    if not isinstance(value, str) or not _YEAR_MONTH_RE.match(value):
        raise UserInputError(
            "year_month 형식은 YYYY-MM 이어야 합니다.", value=value
        )


def _ensure_category_exists(cat_repo: CategoryRepository, name: str) -> None:
    for category in cat_repo.iter_categories():
        if category.name == name:
            return
    raise UserInputError("등록되지 않은 카테고리입니다.", category=name)


def add_transaction(
    *,
    tx_repo: TransactionRepository,
    cat_repo: CategoryRepository,
    type: str,
    date_str: str,
    category: str,
    amount: object,
    memo: str = "",
    tags: Sequence[str] | None = None,
    id_factory: Callable[[], str] = _default_id_factory,
) -> Transaction:
    """Validate user input and append a new transaction.

    Raises :class:`UserInputError` (exit code 2) if any field is invalid.
    """
    parsed_date = _parse_iso_date(date_str)
    if type not in TRANSACTION_TYPES:
        raise UserInputError(
            "type 은 income/expense 중 하나여야 합니다.", value=type
        )
    parsed_amount = _parse_positive_int(amount, field_name="amount")
    if not category:
        raise UserInputError("category 는 비어있을 수 없습니다.")
    _ensure_category_exists(cat_repo, category)
    transaction = Transaction(
        id=id_factory(),
        type=type,
        date=parsed_date,
        amount=parsed_amount,
        category=category,
        memo=memo,
        tags=[t for t in (tags or []) if t],
    )
    tx_repo.append(transaction)
    return transaction


def list_transactions(
    tx_repo: TransactionRepository, limit: int
) -> Iterator[Transaction]:
    """Yield transactions newest-first, capped at ``limit``.

    Sorting requires materialising the file once but reads still go
    through the underlying generator (plan.md §6, subject §4.7).
    """
    if limit <= 0:
        raise UserInputError("limit 는 양수여야 합니다.", value=limit)
    ordered = sorted(
        tx_repo.iter_transactions(),
        key=lambda t: (t.date, t.id),
        reverse=True,
    )
    yield from ordered[:limit]


def _matches_filters(tx: Transaction, filters: TransactionFilters) -> bool:
    if filters.from_date and tx.date < filters.from_date:
        return False
    if filters.to_date and tx.date > filters.to_date:
        return False
    if filters.category and tx.category != filters.category:
        return False
    if filters.type and tx.type != filters.type:
        return False
    if filters.query and filters.query not in tx.memo:
        return False
    if filters.tag and filters.tag not in tx.tags:
        return False
    return True


def search_transactions(
    tx_repo: TransactionRepository, filters: TransactionFilters
) -> Iterator[Transaction]:
    """Yield filtered transactions newest-first."""
    matched = (
        tx for tx in tx_repo.iter_transactions() if _matches_filters(tx, filters)
    )
    yield from sorted(matched, key=lambda t: (t.date, t.id), reverse=True)


def summarize_month(
    *,
    tx_repo: TransactionRepository,
    budget_repo: BudgetRepository,
    year_month: str,
    top_n: int = 5,
) -> MonthlySummary:
    """Aggregate a single month's totals, top categories and budget usage."""
    _validate_year_month(year_month)
    if top_n <= 0:
        raise UserInputError("top_n 는 양수여야 합니다.", value=top_n)
    income = 0
    expense = 0
    by_category: dict[str, int] = {}
    for tx in tx_repo.iter_transactions():
        if tx.date.strftime("%Y-%m") != year_month:
            continue
        if tx.type == "income":
            income += tx.amount
        else:
            expense += tx.amount
            by_category[tx.category] = by_category.get(tx.category, 0) + tx.amount
    top_categories = [
        CategoryAmount(category=name, amount=amount)
        for name, amount in sorted(
            by_category.items(), key=lambda item: (-item[1], item[0])
        )[:top_n]
    ]
    budget = get_budget(budget_repo, year_month)
    usage = _compute_budget_usage(budget, expense)
    return MonthlySummary(
        year_month=year_month,
        income=income,
        expense=expense,
        balance=income - expense,
        top_categories=top_categories,
        budget_usage=usage,
    )


def _compute_budget_usage(budget: Budget | None, expense: int) -> BudgetUsage | None:
    if budget is None:
        return None
    ratio = expense / budget.amount if budget.amount else 0.0
    return BudgetUsage(
        limit=budget.amount,
        used=expense,
        ratio=ratio,
        over_amount=max(0, expense - budget.amount),
    )


def set_budget(
    repo: BudgetRepository, year_month: str, amount: object
) -> Budget:
    """Insert or replace the budget for ``year_month``."""
    _validate_year_month(year_month)
    parsed_amount = _parse_positive_int(amount, field_name="amount")
    budget = Budget(year_month=year_month, amount=parsed_amount)
    repo.upsert(budget)
    return budget


def get_budget(repo: BudgetRepository, year_month: str) -> Budget | None:
    """Return the budget set for ``year_month`` or ``None`` if absent."""
    _validate_year_month(year_month)
    for budget in repo.iter_budgets():
        if budget.year_month == year_month:
            return budget
    return None


def add_category(repo: CategoryRepository, name: str) -> Category:
    """Append a new unique category (plan.md §9.5)."""
    cleaned = (name or "").strip()
    if not cleaned:
        raise UserInputError("카테고리 이름은 비어있을 수 없습니다.")
    for existing in repo.iter_categories():
        if existing.name == cleaned:
            raise UserInputError("이미 존재하는 카테고리입니다.", name=cleaned)
    category = Category(name=cleaned)
    repo.append(category)
    return category


def remove_category(
    *,
    tx_repo: TransactionRepository,
    cat_repo: CategoryRepository,
    name: str,
) -> None:
    """Remove a category, blocking the call if any transaction still uses it."""
    in_use = sum(1 for tx in tx_repo.iter_transactions() if tx.category == name)
    if in_use:
        raise CategoryInUseError(
            "사용 중인 카테고리는 삭제할 수 없습니다.",
            name=name,
            in_use=in_use,
        )
    existing = list(cat_repo.iter_categories())
    if not any(c.name == name for c in existing):
        raise NotFoundError("해당 카테고리를 찾을 수 없습니다.", name=name)
    cat_repo.replace_all([c for c in existing if c.name != name])


def bootstrap_default_categories(repo: CategoryRepository) -> list[Category]:
    """Seed default categories on a fresh installation (subject §4.5 안 A).

    Idempotent: returns ``[]`` if any category already exists.
    """
    for _existing in repo.iter_categories():
        return []
    seeded: list[Category] = []
    for name in DEFAULT_CATEGORIES:
        category = Category(name=name)
        repo.append(category)
        seeded.append(category)
    return seeded


__all__ = [
    "BudgetAppError",
    "BudgetUsage",
    "CategoryAmount",
    "DEFAULT_CATEGORIES",
    "MonthlySummary",
    "TransactionFilters",
    "add_category",
    "add_transaction",
    "bootstrap_default_categories",
    "get_budget",
    "list_transactions",
    "remove_category",
    "search_transactions",
    "set_budget",
    "summarize_month",
]
