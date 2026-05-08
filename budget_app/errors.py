"""Domain exceptions for budget_app (plan.md §7, §9, §12).

Services raise these instead of bare ``ValueError`` so that the CLI layer
(via ``decorators.translate_errors``) can render plan §9 messages and
exit with the right status code (subject §4.15).

Exit code policy:
    UserInputError -> 2 (input/validation failure)
    other domain errors -> 1 (operational failure)
"""

from __future__ import annotations

from typing import Any

EXIT_CODE_USER_INPUT = 2
EXIT_CODE_OPERATIONAL = 1


class BudgetAppError(Exception):
    """Base class for all domain errors."""

    exit_code: int = EXIT_CODE_OPERATIONAL
    default_hint: str = ""

    def __init__(
        self,
        message: str,
        /,
        *,
        hint: str | None = None,
        **context: Any,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint if hint is not None else self.default_hint
        self.context = context

    def __str__(self) -> str:
        if not self.context:
            return self.message
        rendered = " ".join(f"{key}={value}" for key, value in self.context.items())
        return f"{self.message} {rendered}"


class UserInputError(BudgetAppError):
    """Raised when user-supplied input fails validation."""

    exit_code = EXIT_CODE_USER_INPUT


class NotFoundError(BudgetAppError):
    """Raised when a referenced record (e.g. transaction id) is missing."""

    exit_code = EXIT_CODE_OPERATIONAL
    default_hint = "list 명령으로 id 를 확인하세요."


class CategoryInUseError(BudgetAppError):
    """Raised when removing a category that is still referenced by transactions."""

    exit_code = EXIT_CODE_OPERATIONAL
    default_hint = "해당 거래들의 카테고리를 먼저 변경하세요."
