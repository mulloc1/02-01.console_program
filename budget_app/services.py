"""Business logic for budget_app (plan.md §6, §11).

Services are pure orchestration: they receive repositories from
``budget_app.repositories`` as parameters, validate the input, and either
yield/return domain objects or raise :mod:`budget_app.errors`. I/O lives
inside the repositories so tests can swap in temporary directories
(.cursorrules §4 SRP).

CSV import/export is intentionally deferred to Phase 2.5.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Callable, Iterator, Sequence

from budget_app.errors import CategoryInUseError, NotFoundError, UserInputError
from budget_app.models import Budget, Category, Transaction
from budget_app.repositories import (
    BudgetRepository,
    CategoryRepository,
    TransactionRepository,
)
from budget_app.types import BudgetUsage, CategoryAmount, MonthlySummary, TransactionFilters
from budget_app.utils import (
    default_id_factory,
    ensure_category_exists,
    parse_iso_date,
    parse_positive_int,
    validate_transaction_type,
    validate_year_month,
)


DEFAULT_CATEGORIES: tuple[str, ...] = ("food", "transport", "rent", "etc")


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
    id_factory: Callable[[], str] = default_id_factory,
) -> Transaction:
    """Validate user input and append a new transaction.

    Raises :class:`UserInputError` (exit code 2) if any field is invalid.
    """
    parsed_date = parse_iso_date(date_str)
    validate_transaction_type(type)
    parsed_amount = parse_positive_int(amount, field_name="amount")
    ensure_category_exists(cat_repo, category)
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


def update_transaction(
    *,
    tx_repo: TransactionRepository,
    cat_repo: CategoryRepository,
    id: str,
    type: str | None = None,
    date_str: str | None = None,
    category: str | None = None,
    amount: object | None = None,
    memo: str | None = None,
    tags: Sequence[str] | None = None,
) -> tuple[Transaction, Transaction]:
    """Apply provided fields to the transaction with ``id``; return ``(before, after)``.

    Validates only the fields the caller actually supplied so the CLI can
    layer plan §9.6 partial updates on top. Raises :class:`NotFoundError`
    when the id does not exist (exit code 1) and :class:`UserInputError`
    on any field-level failure (exit code 2). Persistence uses the same
    atomic ``replace_all`` rewrite as ``delete_transaction`` to avoid
    leaving the JSONL store half-written (plan.md §5).
    """
    transactions = list(tx_repo.iter_transactions())
    target_index = next(
        (idx for idx, tx in enumerate(transactions) if tx.id == id), None
    )
    if target_index is None:
        raise NotFoundError("해당 id 의 거래를 찾을 수 없습니다.", id=id)
    before = transactions[target_index]

    changes: dict[str, object] = {}
    if date_str is not None:
        changes["date"] = parse_iso_date(date_str)
    if type is not None:
        validate_transaction_type(type)
        changes["type"] = type
    if amount is not None:
        changes["amount"] = parse_positive_int(amount, field_name="amount")
    if category is not None:
        ensure_category_exists(cat_repo, category)
        changes["category"] = category
    if memo is not None:
        changes["memo"] = memo
    if tags is not None:
        changes["tags"] = [t for t in tags if t]

    after = replace(before, **changes)
    transactions[target_index] = after
    tx_repo.replace_all(transactions)
    return before, after


def delete_transaction(
    *,
    tx_repo: TransactionRepository,
    id: str,
) -> Transaction:
    """Remove the transaction with ``id`` and return the deleted record.

    Raises :class:`NotFoundError` (exit code 1) when ``id`` is missing.
    Other rows are preserved through the atomic rewrite.
    """
    transactions = list(tx_repo.iter_transactions())
    target = next((tx for tx in transactions if tx.id == id), None)
    if target is None:
        raise NotFoundError("해당 id 의 거래를 찾을 수 없습니다.", id=id)
    tx_repo.replace_all(tx for tx in transactions if tx.id != id)
    return target


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
    validate_year_month(year_month)
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
    validate_year_month(year_month)
    parsed_amount = parse_positive_int(amount, field_name="amount")
    budget = Budget(year_month=year_month, amount=parsed_amount)
    repo.upsert(budget)
    return budget


def get_budget(repo: BudgetRepository, year_month: str) -> Budget | None:
    """Return the budget set for ``year_month`` or ``None`` if absent."""
    validate_year_month(year_month)
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


__all__ = [
    "DEFAULT_CATEGORIES",
    "add_category",
    "add_transaction",
    "delete_transaction",
    "get_budget",
    "list_transactions",
    "remove_category",
    "search_transactions",
    "set_budget",
    "summarize_month",
    "update_transaction",
]
