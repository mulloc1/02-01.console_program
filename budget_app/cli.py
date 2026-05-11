"""Per-command handlers for budget_app (plan.md §8, §9).

The argparse graph is built in :mod:`budget_app.parser`. Orchestration
(parse → bootstrap → dispatch) lives in :mod:`budget_app.main`.

Handlers compose repositories and :mod:`budget_app.services`; stdout/stderr
formatting follows plan.md §9.9. Cross-cutting concerns (error translation
and optional elapsed time) ride in via :mod:`budget_app.decorators`.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterator, Sequence

from budget_app.csv_io import export_csv, import_csv
from budget_app.decorators import (
    measure_time,
    translate_errors,
)
from budget_app.errors import (
    BudgetAppError,
    UserInputError,
)
from budget_app.models import Transaction
from budget_app.repositories import (
    BudgetRepository,
    CategoryRepository,
    TransactionRepository,
)
from budget_app.types import MonthlySummary, TransactionFilters
from budget_app.services import (
    add_category,
    add_transaction,
    delete_transaction,
    list_transactions,
    remove_category,
    search_transactions,
    set_budget,
    summarize_month,
    update_transaction,
)
from budget_app.utils import (
    ensure_category_exists,
    parse_iso_date,
    parse_positive_int,
    validate_transaction_type,
    validate_year_month,
)

if TYPE_CHECKING:
    from budget_app.main import _Paths


def _format_amount(value: int) -> str:
    return f"{value:,}"


def _format_tx_table(
    transactions: Sequence[Transaction],
    *,
    total_count: int,
    limit: int | None,
) -> str:
    """Render plan.md §9.2 table (header, dashes, rows, footer total)."""
    headers = ("date", "type", "amount", "category", "id", "memo")
    rows: list[tuple[str, ...]] = []
    for tx in transactions:
        rows.append(
            (
                tx.date.isoformat(),
                tx.type,
                _format_amount(tx.amount),
                tx.category,
                tx.id,
                tx.memo,
            )
        )

    widths = [
        max(len(h), max((len(r[i]) for r in rows), default=0))
        for i, h in enumerate(headers)
    ]

    def _format_row(row: tuple[str, ...], *, header: bool) -> str:
        cells: list[str] = []
        for i, cell in enumerate(row):
            if i == 2 and not header:
                cells.append(cell.rjust(widths[i]))
            else:
                cells.append(cell.ljust(widths[i]))
        return "  ".join(cells).rstrip()

    lines = [_format_row(headers, header=True)]
    lines.append("  ".join("-" * w for w in widths))
    for row in rows:
        lines.append(_format_row(row, header=False))
    if limit is not None:
        lines.append(f"total: {total_count} (limit={limit})")
    else:
        lines.append(f"total: {total_count}")
    return "\n".join(lines)


def _format_summary(summary: MonthlySummary, *, top_n: int) -> str:
    """Render plan.md §9.3 summary block."""
    if summary.is_empty:
        return f"[Summary] {summary.year_month} - 데이터 없음"

    label_width = 8
    formatted_amounts = {
        "income:": _format_amount(summary.income),
        "expense:": _format_amount(summary.expense),
        "balance:": _format_amount(summary.balance),
    }
    amount_width = max(12, max(len(v) for v in formatted_amounts.values()))

    lines = [f"[Summary] {summary.year_month}"]
    for label in ("income:", "expense:", "balance:"):
        lines.append(
            f"{label:<{label_width}}{formatted_amounts[label]:>{amount_width}}"
        )

    if summary.top_categories:
        lines.append("")
        lines.append(f"[Top expenses by category] (TOP {top_n})")
        cat_pad = max(len(c.category) for c in summary.top_categories) + 3
        amount_strs = [_format_amount(c.amount) for c in summary.top_categories]
        amt_pad = max(len(a) for a in amount_strs)
        for rank, (c, amount_str) in enumerate(
            zip(summary.top_categories, amount_strs), start=1
        ):
            pct = (c.amount / summary.expense * 100) if summary.expense else 0.0
            lines.append(
                f"{rank}. {c.category:<{cat_pad}}{amount_str:>{amt_pad}} ({pct:.1f}%)"
            )

    if summary.budget_usage is not None:
        usage = summary.budget_usage
        pct = usage.ratio * 100
        head = (
            f"[Budget] limit {_format_amount(usage.limit)} "
            f"/ used {_format_amount(usage.used)} ({pct:.1f}%)"
        )
        if usage.is_over:
            lines.append(
                f"{head} [WARN] 예산 초과 {_format_amount(usage.over_amount)}"
            )
        else:
            lines.append(f"{head} [OK]")

    return "\n".join(lines)


def _format_update_diff(before: Transaction, after: Transaction) -> Iterator[str]:
    """Yield ``[INFO] field: old -> new`` lines for changed fields (plan §9.6)."""
    if before.date != after.date:
        yield f"[INFO] date: {before.date.isoformat()} -> {after.date.isoformat()}"
    if before.type != after.type:
        yield f"[INFO] type: {before.type} -> {after.type}"
    if before.category != after.category:
        yield f"[INFO] category: {before.category} -> {after.category}"
    if before.amount != after.amount:
        yield (
            f"[INFO] amount: {_format_amount(before.amount)} "
            f"-> {_format_amount(after.amount)}"
        )
    if before.memo != after.memo:
        yield f'[INFO] memo: "{before.memo}" -> "{after.memo}"'
    if list(before.tags) != list(after.tags):
        yield f"[INFO] tags: {list(before.tags)} -> {list(after.tags)}"


def _print_field_error(exc: UserInputError) -> None:
    """Render a UserInputError on stderr without aborting (used by add prompts)."""
    print(f"[ERROR] {exc}", file=sys.stderr)
    if exc.hint:
        print(f"힌트: {exc.hint}", file=sys.stderr)


def _prompt_until_valid(prompt: str, validator: Callable[[str], None]) -> str:
    """Loop ``input(prompt)`` until ``validator`` accepts the value."""
    while True:
        raw = input(prompt)
        try:
            validator(raw)
            return raw
        except UserInputError as exc:
            _print_field_error(exc)


def _build_export_filters(args: argparse.Namespace) -> TransactionFilters:
    """Translate ``export`` options into a :class:`TransactionFilters`."""
    if args.month:
        validate_year_month(args.month)
        year_str, month_str = args.month.split("-")
        year, month = int(year_str), int(month_str)
        first = date(year, month, 1)
        if month == 12:
            last = date(year, 12, 31)
        else:
            last = date(year, month + 1, 1) - timedelta(days=1)
        return TransactionFilters(from_date=first, to_date=last)

    from_date = parse_iso_date(args.from_date) if args.from_date else None
    to_date = parse_iso_date(args.to_date) if args.to_date else None
    return TransactionFilters(from_date=from_date, to_date=to_date)


@translate_errors
@measure_time
def _handle_add(
    args: argparse.Namespace, paths: _Paths
) -> int:
    tx_repo = TransactionRepository(path=paths.transactions)
    cat_repo = CategoryRepository(path=paths.categories)

    raw_date = _prompt_until_valid(
        "date (YYYY-MM-DD): ", lambda v: parse_iso_date(v)
    )

    raw_type = _prompt_until_valid(
        "type (income/expense): ", validate_transaction_type
    )

    category_names = [c.name for c in cat_repo.iter_categories()]
    if category_names:
        print(f"[INFO] category options: {', '.join(category_names)}")

    raw_category = _prompt_until_valid(
        "category: ", lambda v: ensure_category_exists(cat_repo, v)
    )
    raw_amount = _prompt_until_valid(
        "amount: ", lambda v: parse_positive_int(v, field_name="amount")
    )

    raw_memo = input("memo (optional): ")
    raw_tags = input("tags (comma separated, optional): ")
    tags = [t.strip() for t in raw_tags.split(",") if t.strip()] if raw_tags else []

    transaction = add_transaction(
        tx_repo=tx_repo,
        cat_repo=cat_repo,
        type=raw_type,
        date_str=raw_date,
        category=raw_category,
        amount=raw_amount,
        memo=raw_memo,
        tags=tags,
    )
    print(f"[OK] 거래가 저장되었습니다. id={transaction.id}")
    return 0


@translate_errors
@measure_time
def _handle_list(
    args: argparse.Namespace, paths: _Paths
) -> int:
    tx_repo = TransactionRepository(path=paths.transactions)
    transactions = list(list_transactions(tx_repo, args.limit))
    if not transactions:
        print("거래 내역이 없습니다.")
        return 0
    print(
        _format_tx_table(
            transactions, total_count=len(transactions), limit=args.limit
        )
    )
    return 0


@translate_errors
@measure_time
def _handle_search(
    args: argparse.Namespace, paths: _Paths
) -> int:
    tx_repo = TransactionRepository(path=paths.transactions)
    from_date = parse_iso_date(args.from_date) if args.from_date else None
    to_date = parse_iso_date(args.to_date) if args.to_date else None
    if args.type:
        validate_transaction_type(args.type)

    filters = TransactionFilters(
        from_date=from_date,
        to_date=to_date,
        category=args.category,
        type=args.type,
        query=args.query,
        tag=args.tag,
    )
    transactions = list(search_transactions(tx_repo, filters))
    if not transactions:
        print("조건에 맞는 거래가 없습니다.")
        return 0
    print(
        _format_tx_table(transactions, total_count=len(transactions), limit=None)
    )
    return 0


@translate_errors
@measure_time
def _handle_summary(
    args: argparse.Namespace, paths: _Paths
) -> int:
    tx_repo = TransactionRepository(path=paths.transactions)
    budget_repo = BudgetRepository(path=paths.budgets)
    summary = summarize_month(
        tx_repo=tx_repo,
        budget_repo=budget_repo,
        year_month=args.month,
        top_n=args.top_n,
    )
    print(_format_summary(summary, top_n=args.top_n))
    return 0


@translate_errors
@measure_time
def _handle_budget_set(
    args: argparse.Namespace, paths: _Paths
) -> int:
    budget_repo = BudgetRepository(path=paths.budgets)
    budget = set_budget(budget_repo, args.month, args.amount)
    print(
        f"[OK] 예산이 저장되었습니다. month={budget.year_month} "
        f"amount={_format_amount(budget.amount)}"
    )
    return 0


@translate_errors
@measure_time
def _handle_category_add(
    args: argparse.Namespace, paths: _Paths
) -> int:
    cat_repo = CategoryRepository(path=paths.categories)
    name = (args.name or "").strip()
    existing = {c.name for c in cat_repo.iter_categories()}
    if name and name in existing:
        print(f"[WARN] 이미 존재하는 카테고리입니다. name={name}", file=sys.stderr)
        return 0
    category = add_category(cat_repo, args.name)
    print(f"[OK] 카테고리가 추가되었습니다. name={category.name}")
    return 0


@translate_errors
@measure_time
def _handle_category_list(
    args: argparse.Namespace, paths: _Paths
) -> int:
    cat_repo = CategoryRepository(path=paths.categories)
    categories = list(cat_repo.iter_categories())
    for c in categories:
        print(f"- {c.name}")
    print(f"total: {len(categories)}")
    return 0


@translate_errors
@measure_time
def _handle_category_remove(
    args: argparse.Namespace, paths: _Paths
) -> int:
    tx_repo = TransactionRepository(path=paths.transactions)
    cat_repo = CategoryRepository(path=paths.categories)
    remove_category(tx_repo=tx_repo, cat_repo=cat_repo, name=args.name)
    print(f"[OK] 카테고리가 삭제되었습니다. name={args.name}")
    return 0


@translate_errors
@measure_time
def _handle_update(
    args: argparse.Namespace, paths: _Paths
) -> int:
    tx_repo = TransactionRepository(path=paths.transactions)
    cat_repo = CategoryRepository(path=paths.categories)

    tags_value: list[str] | None = None
    if args.tags is not None:
        tags_value = [t.strip() for t in args.tags.split(",") if t.strip()]

    before, after = update_transaction(
        tx_repo=tx_repo,
        cat_repo=cat_repo,
        id=args.id,
        type=args.type,
        date_str=args.date,
        category=args.category,
        amount=args.amount,
        memo=args.memo,
        tags=tags_value,
    )
    print(f"[OK] 거래가 수정되었습니다. id={after.id}")
    for line in _format_update_diff(before, after):
        print(line)
    return 0


@translate_errors
@measure_time
def _handle_delete(
    args: argparse.Namespace, paths: _Paths
) -> int:
    tx_repo = TransactionRepository(path=paths.transactions)
    deleted = delete_transaction(tx_repo=tx_repo, id=args.id)
    print(f"[OK] 거래가 삭제되었습니다. id={deleted.id}")
    return 0


@translate_errors
@measure_time
def _handle_import(
    args: argparse.Namespace, paths: _Paths
) -> int:
    tx_repo = TransactionRepository(path=paths.transactions)
    cat_repo = CategoryRepository(path=paths.categories)
    result = import_csv(
        source=Path(args.source), tx_repo=tx_repo, cat_repo=cat_repo
    )
    if result.is_total_failure:
        raise BudgetAppError(
            "CSV 가져오기에 실패했습니다.",
            file=args.source,
            hint=(
                "헤더가 [date,type,category,amount,memo,tags] 인지, "
                "인코딩이 UTF-8 인지 확인하세요."
            ),
        )
    print(
        f"[OK] CSV 가져오기 완료. 처리 {result.processed}건 "
        f"(성공 {result.success}, 스킵 {len(result.skips)})"
    )
    for skip in result.skips:
        print(f"- skip line {skip.line} (id={skip.row_id}): {skip.reason}")
        rendered_values = ", ".join(
            f"{name}={value!r}" for name, value in skip.row_values.items()
        )
        print(f"  row: {rendered_values}")
    print(f"file: {paths.transactions}")
    return 0


@translate_errors
@measure_time
def _handle_export(
    args: argparse.Namespace, paths: _Paths
) -> int:
    tx_repo = TransactionRepository(path=paths.transactions)
    has_month = bool(args.month)
    has_range = bool(args.from_date) and bool(args.to_date)
    if not has_month and not has_range:
        raise UserInputError(
            "export 는 -month 또는 -from + -to 중 하나가 필수입니다.",
            hint="예) export -out out.csv -month 2026-05",
        )
    filters = _build_export_filters(args)
    written = export_csv(
        target=Path(args.out), tx_repo=tx_repo, filters=filters
    )
    print(f"[OK] CSV 내보내기 완료. 처리 {written}건")
    print(f"file: {args.out}")
    return 0


_HANDLERS: dict[str, Callable[..., int]] = {
    "add": _handle_add,
    "list": _handle_list,
    "search": _handle_search,
    "summary": _handle_summary,
    "update": _handle_update,
    "delete": _handle_delete,
    "import": _handle_import,
    "export": _handle_export,
}

_BUDGET_HANDLERS: dict[str, Callable[..., int]] = {
    "set": _handle_budget_set,
}

_CATEGORY_HANDLERS: dict[str, Callable[..., int]] = {
    "add": _handle_category_add,
    "list": _handle_category_list,
    "remove": _handle_category_remove,
}


def resolve_command_handler(
    args: argparse.Namespace,
) -> Callable[..., int]:
    """Return the handler for ``args.command`` (and nested budget/category action)."""
    if args.command == "budget":
        return _BUDGET_HANDLERS[args.budget_action]
    if args.command == "category":
        return _CATEGORY_HANDLERS[args.category_action]
    return _HANDLERS[args.command]

