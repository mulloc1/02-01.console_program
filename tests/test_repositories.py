"""Tests for JSONL-backed repositories (plan.md §5, §11, §12)."""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr
from datetime import date
from typing import Any

import helpers
from helpers import temp_budget_data_root

from budget_app.models import Budget, Category, Transaction
from budget_app.repositories import (
    BudgetRepository,
    CategoryRepository,
    TransactionRepository,
)


def _make_tx(tx_id: str = "tx1", **overrides: Any) -> Transaction:
    base: dict[str, Any] = {
        "id": tx_id,
        "type": "expense",
        "date": date(2026, 5, 8),
        "amount": 12000,
        "category": "food",
        "memo": "lunch",
        "tags": ["a"],
    }
    base.update(overrides)
    return Transaction(**base)


class HelpersPathsTests(unittest.TestCase):
    def test_temp_budget_data_root_layout(self) -> None:
        # tests/helpers.py가 plan §5 파일명 3종을 그대로 노출하는지 검증한다.
        with temp_budget_data_root() as paths:
            self.assertEqual(paths.transactions.name, helpers.TRANSACTIONS_FILENAME)
            self.assertEqual(paths.categories.name, helpers.CATEGORIES_FILENAME)
            self.assertEqual(paths.budgets.name, helpers.BUDGETS_FILENAME)
            self.assertTrue(paths.root.is_dir())


class TransactionRepositoryTests(unittest.TestCase):
    def test_iter_on_missing_file_yields_empty(self) -> None:
        # 저장소 파일이 없을 때 iter_transactions가 빈 결과를 반환하는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = TransactionRepository(path=paths.transactions)
            self.assertFalse(paths.transactions.exists())
            self.assertEqual(list(repo.iter_transactions()), [])

    def test_append_creates_file_and_round_trips(self) -> None:
        # append로 파일이 생성되고 기록한 거래가 그대로 다시 읽히는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = TransactionRepository(path=paths.transactions)
            tx = _make_tx()
            repo.append(tx)
            self.assertTrue(paths.transactions.exists())
            self.assertEqual(list(repo.iter_transactions()), [tx])

    def test_iter_returns_lazy_generator(self) -> None:
        # 읽기 API가 list가 아닌 yield 기반 제너레이터인지 검증한다.
        with temp_budget_data_root() as paths:
            repo = TransactionRepository(path=paths.transactions)
            repo.append(_make_tx())
            stream = repo.iter_transactions()
            self.assertNotIsInstance(stream, list)
            first = next(stream)
            self.assertIsInstance(first, Transaction)

    def test_replace_all_overwrites_atomically(self) -> None:
        # replace_all이 기존 라인을 모두 새 컬렉션으로 교체하는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = TransactionRepository(path=paths.transactions)
            repo.append(_make_tx("a"))
            repo.append(_make_tx("b"))
            repo.replace_all([_make_tx("c", amount=5000)])
            self.assertEqual([t.id for t in repo.iter_transactions()], ["c"])

    def test_corrupted_line_is_skipped_with_warning(self) -> None:
        # 손상된 JSONL 라인이 있어도 정상 라인은 계속 읽히고 stderr에 [WARN]이 남는지 검증한다.
        with temp_budget_data_root() as paths:
            payload = json.dumps(_make_tx("ok").to_dict(), ensure_ascii=False)
            paths.transactions.write_text(
                "{not valid json\n" + payload + "\n",
                encoding="utf-8",
            )
            repo = TransactionRepository(path=paths.transactions)
            buf = io.StringIO()
            with redirect_stderr(buf):
                loaded = list(repo.iter_transactions())
            self.assertEqual([t.id for t in loaded], ["ok"])
            self.assertIn("[WARN]", buf.getvalue())

    def test_blank_lines_are_ignored(self) -> None:
        # 공백 라인이 섞여 있어도 거래만 yield 되는지 검증한다.
        with temp_budget_data_root() as paths:
            payload = json.dumps(_make_tx("ok").to_dict(), ensure_ascii=False)
            paths.transactions.write_text(
                "\n\n" + payload + "\n\n",
                encoding="utf-8",
            )
            repo = TransactionRepository(path=paths.transactions)
            self.assertEqual([t.id for t in repo.iter_transactions()], ["ok"])

    def test_invalid_payload_line_is_skipped_with_warning(self) -> None:
        # from_dict 단계(KeyError/ValueError) 오류도 라인 스킵 후 계속 읽는지 검증한다.
        with temp_budget_data_root() as paths:
            invalid_payload = json.dumps(
                {
                    "id": "bad",
                    "type": "expense",
                    "date": "2026-05-08",
                    "amount": 12000,
                    # category 누락 -> KeyError 유도
                },
                ensure_ascii=False,
            )
            valid_payload = json.dumps(_make_tx("ok").to_dict(), ensure_ascii=False)
            paths.transactions.write_text(
                invalid_payload + "\n" + valid_payload + "\n",
                encoding="utf-8",
            )
            repo = TransactionRepository(path=paths.transactions)
            buf = io.StringIO()
            with redirect_stderr(buf):
                loaded = list(repo.iter_transactions())
            self.assertEqual([t.id for t in loaded], ["ok"])
            self.assertIn("[WARN] skipping invalid JSONL line:", buf.getvalue())


class CategoryRepositoryTests(unittest.TestCase):
    def test_append_and_iter_round_trip(self) -> None:
        # CategoryRepository append/iter 라운드트립을 검증한다.
        with temp_budget_data_root() as paths:
            repo = CategoryRepository(path=paths.categories)
            repo.append(Category("food"))
            repo.append(Category("salary"))
            self.assertEqual(
                [c.name for c in repo.iter_categories()],
                ["food", "salary"],
            )

    def test_replace_all(self) -> None:
        # replace_all이 카테고리 전체를 교체하는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = CategoryRepository(path=paths.categories)
            repo.append(Category("a"))
            repo.replace_all([Category("x"), Category("y")])
            self.assertEqual([c.name for c in repo.iter_categories()], ["x", "y"])


class BudgetRepositoryTests(unittest.TestCase):
    def test_upsert_inserts_when_new_month(self) -> None:
        # 새로운 월의 예산이 upsert로 새 row로 추가되는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = BudgetRepository(path=paths.budgets)
            repo.upsert(Budget("2026-05", 1_000_000))
            self.assertEqual(
                list(repo.iter_budgets()),
                [Budget("2026-05", 1_000_000)],
            )

    def test_upsert_replaces_same_month(self) -> None:
        # 같은 월에 다시 upsert하면 row 1개로 유지되며 금액만 갱신되는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = BudgetRepository(path=paths.budgets)
            repo.upsert(Budget("2026-05", 1_000_000))
            repo.upsert(Budget("2026-05", 1_500_000))
            self.assertEqual(
                list(repo.iter_budgets()),
                [Budget("2026-05", 1_500_000)],
            )

    def test_upsert_preserves_other_months(self) -> None:
        # 다른 월의 예산은 upsert로 영향받지 않는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = BudgetRepository(path=paths.budgets)
            repo.upsert(Budget("2026-04", 700_000))
            repo.upsert(Budget("2026-05", 1_000_000))
            repo.upsert(Budget("2026-05", 1_500_000))
            loaded = sorted(repo.iter_budgets(), key=lambda b: b.year_month)
            self.assertEqual(
                loaded,
                [Budget("2026-04", 700_000), Budget("2026-05", 1_500_000)],
            )


if __name__ == "__main__":
    unittest.main()
