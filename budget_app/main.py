"""Application entry orchestration (plan.md §8).

``main()`` is the only public entry. Paths/bootstrap helpers are
main-module private (leading ``_``). Parsing uses :mod:`budget_app.parser`;
dispatch uses :func:`budget_app.cli.resolve_command_handler`.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from budget_app.cli import resolve_command_handler
from budget_app.models import Category
from budget_app.parser import build_parser
from budget_app.repositories import CategoryRepository
from budget_app.services import DEFAULT_CATEGORIES


@dataclass(frozen=True)
class _Paths:
    """Resolved JSONL file paths under a ``-data-dir`` root."""

    root: Path
    transactions: Path
    categories: Path
    budgets: Path


def _resolve_paths(data_dir: str) -> _Paths:
    root = Path(data_dir)
    return _Paths(
        root=root,
        transactions=root / "transactions.jsonl",
        categories=root / "categories.jsonl",
        budgets=root / "budgets.jsonl",
    )


def _bootstrap_default_categories(repo: CategoryRepository) -> list[Category]:
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


def main(argv: list[str] | None = None) -> int:
    """Parse ``argv``, bootstrap defaults, and dispatch the matching handler."""
    parser = build_parser()
    args = parser.parse_args(argv)
    paths = _resolve_paths(args.data_dir)
    cat_repo = CategoryRepository(path=paths.categories)
    _bootstrap_default_categories(cat_repo)
    handler = resolve_command_handler(args)
    return handler(args, paths, verbose=args.verbose)


__all__ = ["main"]
