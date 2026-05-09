"""Entry point for ``python -m budget_app`` (plan.md §8).

Delegates to :func:`budget_app.main.main`, then exits with that return code.
Domain errors translated by ``@translate_errors`` raise :class:`SystemExit`
inside the handler, so this wrapper only handles the ordinary int path.
"""

from __future__ import annotations

from budget_app.main import main


if __name__ == "__main__":
    raise SystemExit(main())
