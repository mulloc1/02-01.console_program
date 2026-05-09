"""JSONL-backed repositories for budget_app.

All reads stream via generators (plan.md §5: "must read with ``yield``")
and all whole-file rewrites go through a temp file plus :func:`os.replace`
for atomicity (plan.md §5, §12). Missing files yield empty results and
are auto-created on first write so repositories work on a fresh data
directory (subject §4.5).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, TypeVar

from budget_app.models import Budget, Category, Transaction

T = TypeVar("T")


def _iter_jsonl(
    path: Path,
    factory: Callable[[dict[str, Any]], T],
) -> Iterator[T]:
    """Yield each JSON object from ``path``.

    Missing files yield nothing. Per-line decode/transform failures are
    skipped with a ``[WARN]`` line on stderr so one bad row never aborts
    the whole stream (plan.md §12). Each decoded payload is transformed by
    ``factory`` before yielding.
    """
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fp:
        for lineno, raw in enumerate(fp, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
                yield factory(payload)
            except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
                print(
                    f"[WARN] skipping invalid JSONL line: file={path} "
                    f"line={lineno} reason={exc}",
                    file=sys.stderr,
                )


def _ensure_file(path: Path) -> None:
    """Create the parent directory and an empty file if either is missing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    """Append ``payload`` as one JSON line to ``path`` (creates file if needed)."""
    _ensure_file(path)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False))
        fp.write("\n")


def _atomic_write_jsonl(path: Path, payloads: Iterable[dict[str, Any]]) -> None:
    """Replace ``path`` atomically with the serialised ``payloads``.

    The writer streams ``payloads`` to a sibling temp file and then calls
    :func:`os.replace`, which is atomic on POSIX and Windows.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            for payload in payloads:
                fp.write(json.dumps(payload, ensure_ascii=False))
                fp.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class TransactionRepository:
    """JSONL store for :class:`Transaction` records."""

    path: Path

    def iter_transactions(self) -> Iterator[Transaction]:
        """Yield each persisted transaction in file order."""
        yield from _iter_jsonl(self.path, Transaction.from_dict)

    def append(self, transaction: Transaction) -> None:
        """Append ``transaction`` to the JSONL file."""
        _append_jsonl(self.path, transaction.to_dict())

    def replace_all(self, transactions: Iterable[Transaction]) -> None:
        """Atomically replace the file contents with ``transactions``."""
        _atomic_write_jsonl(self.path, (t.to_dict() for t in transactions))


@dataclass(frozen=True)
class CategoryRepository:
    """JSONL store for :class:`Category` records."""

    path: Path

    def iter_categories(self) -> Iterator[Category]:
        """Yield each persisted category in file order."""
        yield from _iter_jsonl(self.path, Category.from_dict)

    def append(self, category: Category) -> None:
        """Append ``category`` to the JSONL file."""
        _append_jsonl(self.path, category.to_dict())

    def replace_all(self, categories: Iterable[Category]) -> None:
        """Atomically replace the file contents with ``categories``."""
        _atomic_write_jsonl(self.path, (c.to_dict() for c in categories))


@dataclass(frozen=True)
class BudgetRepository:
    """JSONL store for :class:`Budget` records (one row per year_month)."""

    path: Path

    def iter_budgets(self) -> Iterator[Budget]:
        """Yield each persisted budget in file order."""
        yield from _iter_jsonl(self.path, Budget.from_dict)

    def append(self, budget: Budget) -> None:
        """Append ``budget`` to the JSONL file (no year_month uniqueness check)."""
        _append_jsonl(self.path, budget.to_dict())

    def upsert(self, budget: Budget) -> None:
        """Insert or replace the row matching ``budget.year_month`` atomically."""
        merged: list[Budget] = []
        replaced = False
        for current in self.iter_budgets():
            if current.year_month == budget.year_month:
                merged.append(budget)
                replaced = True
            else:
                merged.append(current)
        if not replaced:
            merged.append(budget)
        _atomic_write_jsonl(self.path, (b.to_dict() for b in merged))
