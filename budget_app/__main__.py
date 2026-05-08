"""Entry point for ``python -m budget_app`` (plan.md §8).

Delegates argument parsing and dispatch to :func:`budget_app.cli.main`,
then exits with whatever return code the handler produced. Domain
errors translated by ``@translate_errors`` raise :class:`SystemExit`
themselves, so this wrapper only handles the success path.
"""

from __future__ import annotations

from budget_app.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
