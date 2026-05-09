"""Common cross-cutting decorators (plan.md §7).

Three decorators are provided:

* :func:`log_command` — emit a start/done line on stderr around a CLI handler.
* :func:`translate_errors` — render :class:`BudgetAppError` subclasses as
  user-friendly ``[ERROR]`` messages and exit with the right status code
  (subject §4.15).
* :func:`measure_time` — print elapsed wall time on stderr when the caller
  opts in via ``verbose=True`` or the ``BUDGET_APP_VERBOSE`` environment
  variable.

Phase 2 only defines and unit-tests the decorators; the CLI hookup
happens in Phase 3.
"""

from __future__ import annotations

import functools
import os
import sys
import time
from typing import Any, Callable, TypeVar

from budget_app.errors import BudgetAppError

F = TypeVar("F", bound=Callable[..., Any])

VERBOSE_ENV_VAR = "BUDGET_APP_VERBOSE"


def log_command(name: str) -> Callable[[F], F]:
    """Log entry/exit of a command to stderr."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            print(f"[INFO] {name} start", file=sys.stderr)
            result = func(*args, **kwargs)
            print(f"[INFO] {name} done", file=sys.stderr)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


def translate_errors(func: F) -> F:
    """Convert :class:`BudgetAppError` to ``[ERROR]`` output and exit code."""

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
    """Print elapsed wall time on stderr when verbose mode is enabled."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Consume verbose from kwargs so handler signatures can stay clean.
        verbose = bool(kwargs.pop("verbose", False))
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            if verbose or bool(os.environ.get(VERBOSE_ENV_VAR)):
                elapsed_ms = (time.perf_counter() - start) * 1000
                print(
                    f"[INFO] {func.__name__} elapsed={elapsed_ms:.2f}ms",
                    file=sys.stderr,
                )

    return wrapper  # type: ignore[return-value]


__all__ = [
    "VERBOSE_ENV_VAR",
    "log_command",
    "measure_time",
    "translate_errors",
]
