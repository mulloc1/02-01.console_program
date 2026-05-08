"""CSV import/export for budget_app (plan.md §6, §9.7; subject §4.13).

This module is a thin data layer on top of :mod:`budget_app.services` and
:mod:`budget_app.repositories`. It owns the CSV schema, decoding rules, and
per-row skip semantics, but delegates business validation to the helpers
already exercised by the rest of the service layer. CLI-side rendering of
import/export results lives in Phase 3 — here we only return structured
``ImportResult`` data.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from budget_app.errors import UserInputError
from budget_app.models import TRANSACTION_TYPES, Transaction
from budget_app.repositories import (
    CategoryRepository,
    TransactionRepository,
)
from budget_app.services import (
    TransactionFilters,
    _default_id_factory,
    _ensure_category_exists,
    _parse_iso_date,
    _parse_positive_int,
    search_transactions,
)


EXPECTED_CSV_HEADER: tuple[str, ...] = (
    "date",
    "type",
    "category",
    "amount",
    "memo",
    "tags",
)


@dataclass(frozen=True)
class ImportSkip:
    """A single row that was skipped during import.

    ``line`` is the 1-based line number in the source file (header is
    line 1, so data rows start at 2). ``reason`` is a stable, lowercased
    English phrase suitable for direct display in plan §9.7's example
    output (``invalid amount "-100"`` etc.).
    """

    line: int
    reason: str


@dataclass(frozen=True)
class ImportResult:
    """Aggregate outcome of an :func:`import_csv` call."""

    processed: int
    success: int
    skips: list[ImportSkip] = field(default_factory=list)

    @property
    def is_total_failure(self) -> bool:
        """Return True when at least one row was processed but none succeeded."""
        return self.processed > 0 and self.success == 0


class _SkipRow(Exception):
    """Internal marker raised when a CSV row should be recorded as a skip."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _parse_row(
    row: dict[str, str | None],
    *,
    cat_repo: CategoryRepository,
    id_factory: Callable[[], str],
) -> Transaction:
    """Translate a ``csv.DictReader`` row into a :class:`Transaction`.

    Raises :class:`_SkipRow` with a CSV-friendly reason when validation
    fails. The caller wraps it into :class:`ImportSkip` together with the
    file's line number so a single bad row never aborts the run
    (plan.md §6, §9.7).
    """
    for field_name in ("date", "type", "category", "amount"):
        value = row.get(field_name)
        if value is None or value == "":
            raise _SkipRow(f'missing field "{field_name}"')

    raw_date = (row.get("date") or "").strip()
    try:
        parsed_date = _parse_iso_date(raw_date)
    except UserInputError:
        raise _SkipRow(f'invalid date "{raw_date}"')

    raw_type = (row.get("type") or "").strip()
    if raw_type not in TRANSACTION_TYPES:
        raise _SkipRow(f'invalid type "{raw_type}"')

    raw_amount = (row.get("amount") or "").strip()
    try:
        amount = _parse_positive_int(raw_amount, field_name="amount")
    except UserInputError:
        raise _SkipRow(f'invalid amount "{raw_amount}"')

    category = (row.get("category") or "").strip()
    try:
        _ensure_category_exists(cat_repo, category)
    except UserInputError:
        raise _SkipRow(f'unknown category "{category}"')

    memo = row.get("memo") or ""
    raw_tags = row.get("tags") or ""
    tags = [token.strip() for token in raw_tags.split(",") if token.strip()]

    return Transaction(
        id=id_factory(),
        type=raw_type,
        date=parsed_date,
        amount=amount,
        category=category,
        memo=memo,
        tags=tags,
    )


def import_csv(
    *,
    source: Path,
    tx_repo: TransactionRepository,
    cat_repo: CategoryRepository,
    id_factory: Callable[[], str] = _default_id_factory,
) -> ImportResult:
    """Stream rows from ``source`` and append valid ones to ``tx_repo``.

    Failures are collected as :class:`ImportSkip` entries so callers can
    show a partial-success summary. Header or encoding problems abort the
    entire run via :class:`UserInputError` (no rows are appended).
    """
    if not source.exists():
        raise UserInputError(
            "CSV 파일을 찾을 수 없습니다.",
            file=str(source),
        )

    try:
        fp = source.open("r", encoding="utf-8", newline="")
    except UnicodeDecodeError:
        raise UserInputError(
            "CSV 인코딩이 UTF-8 이 아닙니다.",
            file=str(source),
            hint="UTF-8 로 저장 후 다시 시도하세요.",
        )

    processed = 0
    success = 0
    skips: list[ImportSkip] = []
    try:
        reader = csv.DictReader(fp)
        try:
            actual_header = tuple(reader.fieldnames or ())
        except UnicodeDecodeError:
            raise UserInputError(
                "CSV 인코딩이 UTF-8 이 아닙니다.",
                file=str(source),
                hint="UTF-8 로 저장 후 다시 시도하세요.",
            )
        if actual_header != EXPECTED_CSV_HEADER:
            raise UserInputError(
                "CSV 헤더 스키마가 다릅니다.",
                expected=list(EXPECTED_CSV_HEADER),
                actual=list(actual_header),
                hint=f"헤더가 {list(EXPECTED_CSV_HEADER)} 인지 확인하세요.",
            )

        try:
            for line_no, row in enumerate(reader, start=2):
                processed += 1
                try:
                    transaction = _parse_row(
                        row, cat_repo=cat_repo, id_factory=id_factory
                    )
                except _SkipRow as exc:
                    skips.append(ImportSkip(line=line_no, reason=exc.reason))
                    continue
                tx_repo.append(transaction)
                success += 1
        except UnicodeDecodeError:
            raise UserInputError(
                "CSV 인코딩이 UTF-8 이 아닙니다.",
                file=str(source),
                hint="UTF-8 로 저장 후 다시 시도하세요.",
            )
    finally:
        fp.close()

    return ImportResult(processed=processed, success=success, skips=skips)


def export_csv(
    *,
    target: Path,
    tx_repo: TransactionRepository,
    filters: TransactionFilters,
) -> int:
    """Write filtered transactions to ``target`` as CSV.

    The header is always written first; an empty filter result yields a
    file with just the header row and a return value of ``0``. CLI-level
    requirements (e.g. enforcing ``-month`` or ``-from``/``-to``) belong
    to Phase 3 — this function intentionally accepts any
    :class:`TransactionFilters` (plan.md §9.7).
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(EXPECTED_CSV_HEADER)
        for transaction in search_transactions(tx_repo, filters):
            writer.writerow(
                [
                    transaction.date.isoformat(),
                    transaction.type,
                    transaction.category,
                    str(transaction.amount),
                    transaction.memo,
                    ",".join(transaction.tags),
                ]
            )
            count += 1
    return count
