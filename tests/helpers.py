"""Shared test helpers for budget_app.

Inserts ``src`` into ``sys.path`` so ``import budget_app`` works under both
``python -m unittest discover -s tests`` (run from the project root) and
``pytest`` (which also reads ``pytest.ini``'s ``pythonpath``). Centralising
this here matches the .cursorrules §5 "Shared Test Helpers" guidance.

Also provides a ``temp_budget_data_root`` context manager that mirrors the
on-disk layout fixed in plan.md §5: three JSONL files under a single root
directory.
"""

from __future__ import annotations

import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


TRANSACTIONS_FILENAME = "transactions.jsonl"
CATEGORIES_FILENAME = "categories.jsonl"
BUDGETS_FILENAME = "budgets.jsonl"


@dataclass(frozen=True)
class BudgetDataPaths:
    """Filesystem paths to the three JSONL stores rooted at ``root``."""

    root: Path

    @property
    def transactions(self) -> Path:
        return self.root / TRANSACTIONS_FILENAME

    @property
    def categories(self) -> Path:
        return self.root / CATEGORIES_FILENAME

    @property
    def budgets(self) -> Path:
        return self.root / BUDGETS_FILENAME


@contextmanager
def temp_budget_data_root() -> Iterator[BudgetDataPaths]:
    """Yield a ``BudgetDataPaths`` rooted at a fresh temporary directory."""
    with tempfile.TemporaryDirectory(prefix="budget_app_") as raw:
        yield BudgetDataPaths(root=Path(raw))
