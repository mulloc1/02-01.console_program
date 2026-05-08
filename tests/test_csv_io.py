"""Tests for budget_app.csv_io (plan.md §6, §9.7, §11; subject §4.13)."""

from __future__ import annotations

import csv
import unittest
from datetime import date

import helpers  # noqa: F401  side-effect: extends sys.path so budget_app imports

from budget_app.csv_io import (
    EXPECTED_CSV_HEADER,
    ImportResult,
    export_csv,
    import_csv,
)
from budget_app.errors import UserInputError
from budget_app.models import Category, Transaction
from budget_app.repositories import (
    CategoryRepository,
    TransactionRepository,
)
from budget_app.services import TransactionFilters
from helpers import temp_budget_data_root


class _SequentialIds:
    """Deterministic id factory for tests."""

    def __init__(self, prefix: str = "id") -> None:
        self.prefix = prefix
        self.counter = 0

    def __call__(self) -> str:
        self.counter += 1
        return f"{self.prefix}{self.counter:04d}"


def _seed_categories(repo: CategoryRepository, names: tuple[str, ...]) -> None:
    for name in names:
        repo.append(Category(name=name))


def _write_csv(path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        for row in rows:
            writer.writerow(row)


def _write_bytes(path, payload: bytes) -> None:
    with path.open("wb") as fp:
        fp.write(payload)


class ImportCsvTests(unittest.TestCase):
    def test_all_rows_valid_persists_each_transaction(self) -> None:
        # 모든 행이 유효하면 success=processed 이고 저장소에서 라운드트립 가능해야 한다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            cat_repo = CategoryRepository(path=paths.categories)
            _seed_categories(cat_repo, ("food", "rent"))
            source = paths.root / "input.csv"
            _write_csv(
                source,
                [
                    list(EXPECTED_CSV_HEADER),
                    ["2026-05-01", "expense", "food", "12000", "lunch", "a,b"],
                    ["2026-05-02", "income", "rent", "500000", "salary", ""],
                ],
            )

            result = import_csv(
                source=source,
                tx_repo=tx_repo,
                cat_repo=cat_repo,
                id_factory=_SequentialIds(),
            )

            self.assertEqual(result.processed, 2)
            self.assertEqual(result.success, 2)
            self.assertEqual(result.skips, [])
            self.assertFalse(result.is_total_failure)
            stored = list(tx_repo.iter_transactions())
            self.assertEqual(len(stored), 2)
            self.assertEqual(
                stored[0],
                Transaction(
                    id="id0001",
                    type="expense",
                    date=date(2026, 5, 1),
                    amount=12000,
                    category="food",
                    memo="lunch",
                    tags=["a", "b"],
                ),
            )
            self.assertEqual(stored[1].tags, [])

    def test_partial_success_collects_each_skip_reason(self) -> None:
        # 잘못된 행은 ImportSkip 으로 누적되고 정상 행은 그대로 저장돼야 한다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            cat_repo = CategoryRepository(path=paths.categories)
            _seed_categories(cat_repo, ("food",))
            source = paths.root / "input.csv"
            _write_csv(
                source,
                [
                    list(EXPECTED_CSV_HEADER),
                    ["2026-05-01", "expense", "food", "12000", "ok", ""],
                    ["2026-05-02", "expense", "food", "-100", "neg", ""],
                    ["not-a-date", "expense", "food", "100", "bad date", ""],
                    ["2026-05-04", "BAD", "food", "100", "bad type", ""],
                    ["2026-05-05", "expense", "ghost", "100", "bad cat", ""],
                ],
            )

            result = import_csv(
                source=source,
                tx_repo=tx_repo,
                cat_repo=cat_repo,
                id_factory=_SequentialIds(),
            )

            self.assertEqual(result.processed, 5)
            self.assertEqual(result.success, 1)
            reasons = [skip.reason for skip in result.skips]
            self.assertEqual(
                reasons,
                [
                    'invalid amount "-100"',
                    'invalid date "not-a-date"',
                    'invalid type "BAD"',
                    'unknown category "ghost"',
                ],
            )
            lines = [skip.line for skip in result.skips]
            self.assertEqual(lines, [3, 4, 5, 6])
            stored = list(tx_repo.iter_transactions())
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0].memo, "ok")

    def test_missing_required_field_records_skip(self) -> None:
        # 필수 컬럼이 비어 있으면 missing field 사유로 스킵된다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            cat_repo = CategoryRepository(path=paths.categories)
            _seed_categories(cat_repo, ("food",))
            source = paths.root / "input.csv"
            _write_csv(
                source,
                [
                    list(EXPECTED_CSV_HEADER),
                    ["2026-05-01", "expense", "food", "", "no amount", ""],
                ],
            )

            result = import_csv(
                source=source,
                tx_repo=tx_repo,
                cat_repo=cat_repo,
                id_factory=_SequentialIds(),
            )

            self.assertEqual(result.processed, 1)
            self.assertEqual(result.success, 0)
            self.assertEqual(len(result.skips), 1)
            self.assertEqual(result.skips[0].reason, 'missing field "amount"')
            self.assertTrue(result.is_total_failure)

    def test_header_mismatch_raises_user_input_error(self) -> None:
        # 헤더 스키마가 다르면 UserInputError 가 즉시 발생하고 저장소에 아무 것도 추가되지 않는다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            cat_repo = CategoryRepository(path=paths.categories)
            _seed_categories(cat_repo, ("food",))
            source = paths.root / "input.csv"
            _write_csv(
                source,
                [
                    ["date", "kind", "category", "amount", "memo", "tags"],
                    ["2026-05-01", "expense", "food", "100", "x", ""],
                ],
            )

            with self.assertRaises(UserInputError) as ctx:
                import_csv(
                    source=source,
                    tx_repo=tx_repo,
                    cat_repo=cat_repo,
                    id_factory=_SequentialIds(),
                )
            self.assertEqual(
                ctx.exception.context["expected"], list(EXPECTED_CSV_HEADER)
            )
            self.assertEqual(list(tx_repo.iter_transactions()), [])

    def test_non_utf8_encoding_raises_user_input_error(self) -> None:
        # UTF-8 이 아닌 바이트 입력은 UserInputError 로 변환된다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            cat_repo = CategoryRepository(path=paths.categories)
            _seed_categories(cat_repo, ("food",))
            source = paths.root / "input.csv"
            payload = (
                ",".join(EXPECTED_CSV_HEADER) + "\n"
                "2026-05-01,expense,food,100,\xb1\xc7\xfa,\n"
            ).encode("cp949", errors="replace")
            _write_bytes(source, payload)

            with self.assertRaises(UserInputError) as ctx:
                import_csv(
                    source=source,
                    tx_repo=tx_repo,
                    cat_repo=cat_repo,
                    id_factory=_SequentialIds(),
                )
            self.assertIn("UTF-8", ctx.exception.message)
            self.assertEqual(list(tx_repo.iter_transactions()), [])

    def test_header_only_returns_empty_result(self) -> None:
        # 헤더만 있는 CSV 는 processed=0, success=0, skips=[] 인 빈 결과를 만든다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            cat_repo = CategoryRepository(path=paths.categories)
            _seed_categories(cat_repo, ("food",))
            source = paths.root / "input.csv"
            _write_csv(source, [list(EXPECTED_CSV_HEADER)])

            result = import_csv(
                source=source,
                tx_repo=tx_repo,
                cat_repo=cat_repo,
                id_factory=_SequentialIds(),
            )

            self.assertEqual(
                result, ImportResult(processed=0, success=0, skips=[])
            )
            self.assertFalse(result.is_total_failure)

    def test_is_total_failure_true_when_every_row_skipped(self) -> None:
        # processed > 0 이면서 success == 0 이면 is_total_failure 가 True 가 되어야 한다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            cat_repo = CategoryRepository(path=paths.categories)
            _seed_categories(cat_repo, ("food",))
            source = paths.root / "input.csv"
            _write_csv(
                source,
                [
                    list(EXPECTED_CSV_HEADER),
                    ["bad", "expense", "food", "100", "x", ""],
                    ["2026-05-02", "BAD", "food", "100", "x", ""],
                ],
            )

            result = import_csv(
                source=source,
                tx_repo=tx_repo,
                cat_repo=cat_repo,
                id_factory=_SequentialIds(),
            )

            self.assertEqual(result.processed, 2)
            self.assertEqual(result.success, 0)
            self.assertTrue(result.is_total_failure)
            self.assertEqual(list(tx_repo.iter_transactions()), [])


class ExportCsvTests(unittest.TestCase):
    def _setup_repo(self, paths) -> TransactionRepository:
        tx_repo = TransactionRepository(path=paths.transactions)
        tx_repo.append(
            Transaction(
                id="id0001",
                type="expense",
                date=date(2026, 5, 1),
                amount=12000,
                category="food",
                memo="lunch",
                tags=["a", "b"],
            )
        )
        tx_repo.append(
            Transaction(
                id="id0002",
                type="income",
                date=date(2026, 4, 30),
                amount=500000,
                category="rent",
                memo="salary",
                tags=[],
            )
        )
        tx_repo.append(
            Transaction(
                id="id0003",
                type="expense",
                date=date(2026, 5, 2),
                amount=3000,
                category="food",
                memo="",
                tags=["solo"],
            )
        )
        return tx_repo

    def test_writes_header_and_filtered_rows_newest_first(self) -> None:
        # from/to 필터로 5월 거래만 최신순으로 기록되어야 한다.
        with temp_budget_data_root() as paths:
            tx_repo = self._setup_repo(paths)
            target = paths.root / "out.csv"

            count = export_csv(
                target=target,
                tx_repo=tx_repo,
                filters=TransactionFilters(
                    from_date=date(2026, 5, 1),
                    to_date=date(2026, 5, 31),
                ),
            )

            self.assertEqual(count, 2)
            with target.open("r", encoding="utf-8", newline="") as fp:
                rows = list(csv.reader(fp))
            self.assertEqual(rows[0], list(EXPECTED_CSV_HEADER))
            self.assertEqual(
                rows[1],
                ["2026-05-02", "expense", "food", "3000", "", "solo"],
            )
            self.assertEqual(
                rows[2],
                ["2026-05-01", "expense", "food", "12000", "lunch", "a,b"],
            )

    def test_serialises_tags_with_comma_join(self) -> None:
        # tags 는 ",".join 으로 직렬화되어야 한다.
        with temp_budget_data_root() as paths:
            tx_repo = self._setup_repo(paths)
            target = paths.root / "out.csv"

            export_csv(
                target=target,
                tx_repo=tx_repo,
                filters=TransactionFilters(category="food"),
            )

            with target.open("r", encoding="utf-8", newline="") as fp:
                rows = list(csv.reader(fp))
            tag_columns = [row[5] for row in rows[1:]]
            self.assertIn("a,b", tag_columns)
            self.assertIn("solo", tag_columns)

    def test_empty_result_writes_header_only_and_returns_zero(self) -> None:
        # 매칭 거래가 없으면 헤더만 적히고 0 을 반환한다.
        with temp_budget_data_root() as paths:
            tx_repo = self._setup_repo(paths)
            target = paths.root / "empty.csv"

            count = export_csv(
                target=target,
                tx_repo=tx_repo,
                filters=TransactionFilters(category="ghost"),
            )

            self.assertEqual(count, 0)
            with target.open("r", encoding="utf-8", newline="") as fp:
                rows = list(csv.reader(fp))
            self.assertEqual(rows, [list(EXPECTED_CSV_HEADER)])

    def test_creates_missing_parent_directories(self) -> None:
        # target.parent 가 없어도 자동 생성되어야 한다.
        with temp_budget_data_root() as paths:
            tx_repo = self._setup_repo(paths)
            target = paths.root / "nested" / "deep" / "out.csv"

            count = export_csv(
                target=target,
                tx_repo=tx_repo,
                filters=TransactionFilters(),
            )

            self.assertTrue(target.exists())
            self.assertEqual(count, 3)


class RoundTripTests(unittest.TestCase):
    def test_export_then_import_preserves_row_set(self) -> None:
        # export 결과를 다시 import 해도 동일한 거래가 다시 채워져야 한다.
        with temp_budget_data_root() as paths:
            cat_repo = CategoryRepository(path=paths.categories)
            _seed_categories(cat_repo, ("food", "rent"))
            tx_repo = TransactionRepository(path=paths.transactions)
            tx_repo.append(
                Transaction(
                    id="id0001",
                    type="expense",
                    date=date(2026, 5, 1),
                    amount=12000,
                    category="food",
                    memo="lunch",
                    tags=["a", "b"],
                )
            )
            tx_repo.append(
                Transaction(
                    id="id0002",
                    type="income",
                    date=date(2026, 5, 2),
                    amount=500000,
                    category="rent",
                    memo="salary",
                    tags=[],
                )
            )
            target = paths.root / "snapshot.csv"

            written = export_csv(
                target=target,
                tx_repo=tx_repo,
                filters=TransactionFilters(),
            )
            self.assertEqual(written, 2)

            other_paths = paths
            other_tx_path = other_paths.root / "transactions2.jsonl"
            new_tx_repo = TransactionRepository(path=other_tx_path)
            result = import_csv(
                source=target,
                tx_repo=new_tx_repo,
                cat_repo=cat_repo,
                id_factory=_SequentialIds(prefix="rt"),
            )

            self.assertEqual(result.success, 2)
            self.assertEqual(result.skips, [])
            reimported = list(new_tx_repo.iter_transactions())
            self.assertEqual(len(reimported), 2)
            original_signatures = {
                (
                    tx.type,
                    tx.date.isoformat(),
                    tx.amount,
                    tx.category,
                    tx.memo,
                    tuple(tx.tags),
                )
                for tx in tx_repo.iter_transactions()
            }
            reimported_signatures = {
                (
                    tx.type,
                    tx.date.isoformat(),
                    tx.amount,
                    tx.category,
                    tx.memo,
                    tuple(tx.tags),
                )
                for tx in reimported
            }
            self.assertEqual(original_signatures, reimported_signatures)


if __name__ == "__main__":
    unittest.main()
