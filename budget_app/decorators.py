"""Common cross-cutting decorators (plan.md §7).

Two decorators are provided:

* :func:`translate_errors` — render :class:`BudgetAppError` subclasses as
  user-friendly ``[ERROR]`` messages and exit with the right status code
  (subject §4.15).
* :func:`measure_time` — print elapsed wall time on stderr when the caller
  opts in via ``verbose=True``.

Phase 2 only defines and unit-tests the decorators; the CLI hookup
happens in Phase 3.
"""

from __future__ import annotations

import functools
import sys
import time
from typing import Any, Callable, TypeVar

from budget_app.errors import BudgetAppError

F = TypeVar("F", bound=Callable[..., Any])


def translate_errors(func: F) -> F:
    """Convert :class:`BudgetAppError` to ``[ERROR]`` output and exit code.

    ``wrapper`` is a closure that remembers ``func`` from the outer scope,
    so every call can execute the original handler while adding shared
    error-translation behavior around it.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except BudgetAppError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            if exc.hint:
                print(f"힌트: {exc.hint}", file=sys.stderr)
            raise SystemExit(exc.exit_code)

    return wrapper  # type: ignore[return-value]


def measure_time(func: F) -> F:
    """Print elapsed wall time on stderr when verbose mode is enabled.

    The returned ``wrapper`` closes over ``func`` and measures around it.
    This keeps timing logic separated from each handler's core responsibility.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Consume verbose from kwargs so handler signatures can stay clean.
        verbose = bool(kwargs.pop("verbose", False))
        start = time.perf_counter() if verbose else None
        try:
            return func(*args, **kwargs)
        finally:
            if verbose and start is not None:
                elapsed_ms = (time.perf_counter() - start) * 1000
                print(
                    f"[INFO] {func.__name__} elapsed={elapsed_ms:.2f}ms",
                    file=sys.stderr,
                )

    return wrapper  # type: ignore[return-value]


__all__ = [
    "measure_time",
    "translate_errors",
]
