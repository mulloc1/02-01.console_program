"""Argparse graph for ``budget_app`` (plan.md §8, subject §4.1).

Single-dash ``-help`` and global ``-data-dir`` / ``-verbose`` live here;
per-command behaviour is implemented in :mod:`budget_app.cli`.
"""

from __future__ import annotations

import argparse


def _add_help(parser: argparse.ArgumentParser) -> None:
    """Register the single-dash ``-help`` action on ``parser`` (subject §4.1)."""
    parser.add_argument(
        "-help",
        action="help",
        default=argparse.SUPPRESS,
        help="show this help message and exit",
    )


def build_parser() -> argparse.ArgumentParser:
    """Assemble the full subcommand graph rooted at ``budget_app``."""
    global_parser = argparse.ArgumentParser(add_help=False)
    global_parser.add_argument(
        "-data-dir",
        dest="data_dir",
        default="./data",
        help="data directory root (default: ./data)",
    )
    global_parser.add_argument(
        "-verbose",
        dest="verbose",
        action="store_true",
        default=False,
        help="enable @measure_time elapsed logs on stderr",
    )

    parser = argparse.ArgumentParser(prog="budget_app", add_help=False)
    _add_help(parser)
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    add_p = subparsers.add_parser(
        "add", parents=[global_parser], add_help=False, help="add a transaction"
    )
    _add_help(add_p)

    list_p = subparsers.add_parser(
        "list", parents=[global_parser], add_help=False, help="list transactions"
    )
    _add_help(list_p)
    list_p.add_argument("-limit", dest="limit", type=int, default=20)

    search_p = subparsers.add_parser(
        "search", parents=[global_parser], add_help=False, help="search transactions"
    )
    _add_help(search_p)
    search_p.add_argument("-from", dest="from_date", default=None)
    search_p.add_argument("-to", dest="to_date", default=None)
    search_p.add_argument("-category", dest="category", default=None)
    search_p.add_argument("-type", dest="type", default=None)
    search_p.add_argument("-q", dest="query", default=None)
    search_p.add_argument("-tag", dest="tag", default=None)

    summary_p = subparsers.add_parser(
        "summary", parents=[global_parser], add_help=False, help="monthly summary"
    )
    _add_help(summary_p)
    summary_p.add_argument("-month", dest="month", required=True)
    summary_p.add_argument("-top", dest="top_n", type=int, default=5)

    budget_p = subparsers.add_parser(
        "budget",
        parents=[global_parser],
        add_help=False,
        help="manage monthly budgets",
    )
    _add_help(budget_p)
    budget_sub = budget_p.add_subparsers(dest="budget_action")
    budget_sub.required = True
    budget_set_p = budget_sub.add_parser(
        "set", parents=[global_parser], add_help=False, help="set monthly budget"
    )
    _add_help(budget_set_p)
    budget_set_p.add_argument("-month", dest="month", required=True)
    budget_set_p.add_argument("-amount", dest="amount", required=True)

    category_p = subparsers.add_parser(
        "category",
        parents=[global_parser],
        add_help=False,
        help="manage categories",
    )
    _add_help(category_p)
    category_sub = category_p.add_subparsers(dest="category_action")
    category_sub.required = True
    cat_add_p = category_sub.add_parser(
        "add", parents=[global_parser], add_help=False, help="add a category"
    )
    _add_help(cat_add_p)
    cat_add_p.add_argument("name")
    cat_list_p = category_sub.add_parser(
        "list", parents=[global_parser], add_help=False, help="list categories"
    )
    _add_help(cat_list_p)
    cat_remove_p = category_sub.add_parser(
        "remove", parents=[global_parser], add_help=False, help="remove a category"
    )
    _add_help(cat_remove_p)
    cat_remove_p.add_argument("name")

    update_p = subparsers.add_parser(
        "update",
        parents=[global_parser],
        add_help=False,
        help="update a transaction",
    )
    _add_help(update_p)
    update_p.add_argument("-id", dest="id", required=True)
    update_p.add_argument("-date", dest="date", default=None)
    update_p.add_argument("-type", dest="type", default=None)
    update_p.add_argument("-category", dest="category", default=None)
    update_p.add_argument("-amount", dest="amount", default=None)
    update_p.add_argument("-memo", dest="memo", default=None)
    update_p.add_argument("-tags", dest="tags", default=None)

    delete_p = subparsers.add_parser(
        "delete",
        parents=[global_parser],
        add_help=False,
        help="delete a transaction",
    )
    _add_help(delete_p)
    delete_p.add_argument("-id", dest="id", required=True)

    import_p = subparsers.add_parser(
        "import",
        parents=[global_parser],
        add_help=False,
        help="import transactions from CSV",
    )
    _add_help(import_p)
    import_p.add_argument("-from", dest="source", required=True)

    export_p = subparsers.add_parser(
        "export",
        parents=[global_parser],
        add_help=False,
        help="export transactions to CSV",
    )
    _add_help(export_p)
    export_p.add_argument("-out", dest="out", required=True)
    export_p.add_argument("-month", dest="month", default=None)
    export_p.add_argument("-from", dest="from_date", default=None)
    export_p.add_argument("-to", dest="to_date", default=None)

    return parser


__all__ = ["build_parser"]
