"""Application entry orchestration (plan.md §8).

Parses ``argv``, resolves paths, seeds default categories, then dispatches
to the handler selected by :mod:`budget_app.cli`. Argument parsing and
per-command handlers stay in ``cli``; this module is the thin ``main()``
surface used by :mod:`budget_app.__main__` and tests.
"""

from __future__ import annotations

from budget_app.cli import build_parser, resolve_handler, resolve_paths
from budget_app.repositories import CategoryRepository
from budget_app.services import bootstrap_default_categories


def main(argv: list[str] | None = None) -> int:
    """Parse ``argv``, bootstrap defaults, and dispatch the matching handler."""
    parser = build_parser()
    args = parser.parse_args(argv)
    paths = resolve_paths(args.data_dir)
    cat_repo = CategoryRepository(path=paths.categories)
    bootstrap_default_categories(cat_repo)
    handler = resolve_handler(args)
    return handler(args, paths, verbose=args.verbose)


__all__ = ["main"]
