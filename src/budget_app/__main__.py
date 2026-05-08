"""Entry point for `python -m budget_app`.

Phase 0 only wires a no-op CLI stub so that the module is importable and
runnable without crashing. Real subcommands are added in later phases.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Run the budget_app CLI stub and return a process exit code."""
    args = sys.argv[1:] if argv is None else list(argv)
    if args:
        print(f"budget_app: command not implemented yet: {args[0]}")
    else:
        print("budget_app: scaffolding ready. Use a subcommand (added in Phase 3).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
