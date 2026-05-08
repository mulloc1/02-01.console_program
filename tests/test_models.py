"""Round-trip tests for the budget_app domain dataclasses (plan.md §4)."""

from __future__ import annotations

import unittest
from datetime import date

import helpers  # noqa: F401  side-effect: extends sys.path so budget_app imports

from budget_app.models import Budget, Category, Transaction


class TransactionRoundTripTests(unittest.TestCase):
    def test_to_dict_and_from_dict_round_trip(self) -> None:
        # Transaction.to_dict() <-> from_dict() 동등성을 검증한다.
        tx = Transaction(
            id="abc123def456",
            type="expense",
            date=date(2026, 5, 8),
            amount=12000,
            category="food",
            memo="점심",
            tags=["lunch", "team"],
        )
        restored = Transaction.from_dict(tx.to_dict())
        self.assertEqual(tx, restored)

    def test_to_dict_uses_iso_date(self) -> None:
        # date 필드가 YYYY-MM-DD 문자열로 직렬화되는지 검증한다.
        tx = Transaction(
            id="x",
            type="income",
            date=date(2026, 1, 2),
            amount=1,
            category="salary",
        )
        payload = tx.to_dict()
        self.assertEqual(payload["date"], "2026-01-02")

    def test_from_dict_defaults_memo_and_tags(self) -> None:
        # memo/tags가 누락된 입력에서 기본값으로 채워지는지 검증한다.
        tx = Transaction.from_dict(
            {
                "id": "x",
                "type": "income",
                "date": "2026-01-02",
                "amount": 1,
                "category": "salary",
            }
        )
        self.assertEqual(tx.memo, "")
        self.assertEqual(tx.tags, [])

    def test_from_dict_rejects_unknown_type(self) -> None:
        # type이 income/expense가 아니면 ValueError로 거부되는지 검증한다.
        with self.assertRaises(ValueError):
            Transaction.from_dict(
                {
                    "id": "x",
                    "type": "transfer",
                    "date": "2026-01-02",
                    "amount": 1,
                    "category": "x",
                }
            )

    def test_to_dict_returns_independent_tags_copy(self) -> None:
        # to_dict 결과의 tags 변경이 원본 모델에 전파되지 않는지 검증한다.
        tx = Transaction(
            id="x",
            type="expense",
            date=date(2026, 1, 1),
            amount=1,
            category="x",
            tags=["a"],
        )
        payload = tx.to_dict()
        payload["tags"].append("z")
        self.assertEqual(tx.tags, ["a"])


class CategoryAndBudgetRoundTripTests(unittest.TestCase):
    def test_category_round_trip(self) -> None:
        # Category to_dict/from_dict 라운드트립을 검증한다.
        category = Category(name="food")
        self.assertEqual(Category.from_dict(category.to_dict()), category)

    def test_budget_round_trip(self) -> None:
        # Budget to_dict/from_dict 라운드트립을 검증한다.
        budget = Budget(year_month="2026-05", amount=500_000)
        self.assertEqual(Budget.from_dict(budget.to_dict()), budget)


if __name__ == "__main__":
    unittest.main()
