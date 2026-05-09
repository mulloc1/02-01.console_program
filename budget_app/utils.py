"""Shared input parsing and validation helpers for budget_app.

Used by :mod:`budget_app.services`, :mod:`budget_app.cli`, and
:mod:`budget_app.csv_io`. Module-local helpers stay private with a leading
``_`` in their *defining* module only; anything imported across modules
lives here with public names (.cursorrules §4).
"""

from __future__ import annotations

import re
import uuid
from datetime import date

from budget_app.errors import UserInputError
from budget_app.models import TRANSACTION_TYPES
from budget_app.repositories import CategoryRepository

_YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def default_id_factory() -> str:
    """Return a short unique id for new transactions."""
    return uuid.uuid4().hex[:12]


def parse_iso_date(value: str, *, field_name: str = "date") -> date:
    """Parse ``YYYY-MM-DD``; raise :class:`UserInputError` on failure."""
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise UserInputError(
            f"{field_name} 는 YYYY-MM-DD 형식이어야 합니다.", value=value
        )


def parse_positive_int(value: object, *, field_name: str) -> int:
    """Coerce to a positive int; raise :class:`UserInputError` otherwise."""
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise UserInputError(f"{field_name} 는 정수여야 합니다.", value=value)
    if parsed <= 0:
        raise UserInputError(
            f"{field_name} 는 양수여야 합니다.",
            value=parsed,
            hint="0 보다 큰 정수를 입력하세요.",
        )
    return parsed


def validate_year_month(value: str) -> None:
    """Require ``YYYY-MM`` shape."""
    if not isinstance(value, str) or not _YEAR_MONTH_RE.match(value):
        raise UserInputError(
            "year_month 형식은 YYYY-MM 이어야 합니다.", value=value
        )


def validate_transaction_type(value: str) -> None:
    """Require ``income`` or ``expense``."""
    if value not in TRANSACTION_TYPES:
        raise UserInputError(
            "type 은 income/expense 중 하나여야 합니다.", value=value
        )


def ensure_category_exists(cat_repo: CategoryRepository, name: str) -> None:
    """Require a non-empty category name registered in ``cat_repo``."""
    if not name:
        raise UserInputError("category 는 비어있을 수 없습니다.")
    for category in cat_repo.iter_categories():
        if category.name == name:
            return
    raise UserInputError("등록되지 않은 카테고리입니다.", category=name)


__all__ = [
    "default_id_factory",
    "ensure_category_exists",
    "parse_iso_date",
    "parse_positive_int",
    "validate_transaction_type",
    "validate_year_month",
]
