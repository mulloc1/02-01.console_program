"""Tests for budget_app.cli (plan.md §8, §9, §11)."""

from __future__ import annotations

import contextlib
import csv
import io
import unittest
import unittest.mock
from datetime import date

import helpers  # noqa: F401  side-effect: extends sys.path so budget_app imports

from budget_app import cli
from budget_app.csv_io import EXPECTED_CSV_HEADER
from budget_app.models import Transaction
from budget_app.repositories import (
    BudgetRepository,
    CategoryRepository,
    TransactionRepository,
)
from budget_app.models import Budget, Category
from helpers import temp_budget_data_root


def _run_cli(
    argv: list[str], *, inputs: list[str] | None = None
) -> tuple[int, str, str]:
    """Invoke ``cli.main`` and return ``(exit_code, stdout, stderr)``.

    ``SystemExit`` raised by ``@translate_errors`` (or argparse ``-help``)
    is captured and converted to a numeric exit code so individual tests
    can compare against plan §9.8's ``0 / 1 / 2`` policy uniformly.
    """
    stdout = io.StringIO()
    stderr = io.StringIO()

    def _invoke() -> int:
        try:
            value = cli.main(argv)
        except SystemExit as exc:
            return int(exc.code) if isinstance(exc.code, int) else 0
        return value if isinstance(value, int) else 0

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        if inputs is not None:
            with unittest.mock.patch("builtins.input", side_effect=inputs):
                code = _invoke()
        else:
            code = _invoke()
    return code, stdout.getvalue(), stderr.getvalue()


def _seed_transaction(paths, transaction: Transaction) -> None:
    repo = TransactionRepository(path=paths.transactions)
    repo.append(transaction)


def _seed_category(paths, name: str) -> None:
    repo = CategoryRepository(path=paths.categories)
    existing = {c.name for c in repo.iter_categories()}
    if name not in existing:
        repo.append(Category(name=name))


class HelpAndDispatchTests(unittest.TestCase):
    def test_help_prints_usage_and_exits_zero(self) -> None:
        # -help 옵션은 argparse 도움말을 출력하고 종료 코드 0 으로 끝난다.
        code, stdout, _ = _run_cli(["-help"])
        self.assertEqual(code, 0)
        self.assertIn("usage:", stdout)
        self.assertIn("budget_app", stdout)

    def test_no_subcommand_exits_with_argparse_error(self) -> None:
        # 서브커맨드 누락 시 argparse 가 비-0 종료 코드로 실패한다.
        code, _, _ = _run_cli([])
        self.assertNotEqual(code, 0)


class ListTests(unittest.TestCase):
    def test_empty_list_prints_korean_message(self) -> None:
        # 거래가 하나도 없으면 한국어 안내 문구만 출력한다.
        with temp_budget_data_root() as paths:
            code, stdout, _ = _run_cli(
                ["list", "-data-dir", str(paths.root)]
            )
            self.assertEqual(code, 0)
            self.assertIn("거래 내역이 없습니다.", stdout)

    def test_list_renders_table_with_total_and_limit(self) -> None:
        # 거래가 있으면 헤더+구분선+행+total: N (limit=L) 형식으로 출력된다.
        with temp_budget_data_root() as paths:
            _seed_category(paths, "food")
            _seed_transaction(
                paths,
                Transaction(
                    id="abc123def456",
                    type="expense",
                    date=date(2026, 5, 7),
                    amount=12000,
                    category="food",
                    memo="lunch",
                ),
            )
            code, stdout, _ = _run_cli(
                ["list", "-limit", "5", "-data-dir", str(paths.root)]
            )
            self.assertEqual(code, 0)
            self.assertIn("date", stdout)
            self.assertIn("type", stdout)
            self.assertIn("amount", stdout)
            self.assertIn("12,000", stdout)
            self.assertIn("abc123def456", stdout)
            self.assertIn("total: 1 (limit=5)", stdout)


class SearchTests(unittest.TestCase):
    def test_no_match_prints_korean_message(self) -> None:
        # 검색 결과가 없으면 plan §9.2 의 "조건에 맞는 거래가 없습니다." 문구를 낸다.
        with temp_budget_data_root() as paths:
            code, stdout, _ = _run_cli(
                [
                    "search",
                    "-category",
                    "ghost",
                    "-data-dir",
                    str(paths.root),
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("조건에 맞는 거래가 없습니다.", stdout)

    def test_filters_match_returns_matching_rows_only(self) -> None:
        # 카테고리 + 태그 필터로 매칭된 거래만 테이블에 노출된다.
        with temp_budget_data_root() as paths:
            for tx in (
                Transaction(
                    id="t000000000001",
                    type="expense",
                    date=date(2026, 5, 1),
                    amount=10,
                    category="food",
                    memo="match",
                    tags=["a"],
                ),
                Transaction(
                    id="t000000000002",
                    type="expense",
                    date=date(2026, 5, 2),
                    amount=20,
                    category="food",
                    memo="other",
                    tags=["b"],
                ),
            ):
                _seed_transaction(paths, tx)
            code, stdout, _ = _run_cli(
                [
                    "search",
                    "-category",
                    "food",
                    "-tag",
                    "a",
                    "-data-dir",
                    str(paths.root),
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("match", stdout)
            self.assertNotIn("other", stdout)
            self.assertIn("total: 1", stdout)


class SummaryTests(unittest.TestCase):
    def test_empty_month_prints_specific_marker(self) -> None:
        # 데이터 없는 달은 "- 데이터 없음" 으로 정확히 출력된다.
        with temp_budget_data_root() as paths:
            code, stdout, _ = _run_cli(
                [
                    "summary",
                    "-month",
                    "2026-05",
                    "-data-dir",
                    str(paths.root),
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("[Summary] 2026-05 - 데이터 없음", stdout)

    def test_summary_includes_budget_ok_when_under_limit(self) -> None:
        # 예산 미초과 상태에서는 [Budget] ... [OK] 라인이 함께 출력된다.
        with temp_budget_data_root() as paths:
            _seed_transaction(
                paths,
                Transaction(
                    id="t1",
                    type="expense",
                    date=date(2026, 5, 1),
                    amount=180000,
                    category="food",
                ),
            )
            BudgetRepository(path=paths.budgets).upsert(
                Budget(year_month="2026-05", amount=1000000)
            )
            code, stdout, _ = _run_cli(
                [
                    "summary",
                    "-month",
                    "2026-05",
                    "-data-dir",
                    str(paths.root),
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("[Summary] 2026-05", stdout)
            self.assertIn("expense:", stdout)
            self.assertIn("[Budget] limit 1,000,000 / used 180,000", stdout)
            self.assertIn("[OK]", stdout)

    def test_summary_warns_when_budget_exceeded(self) -> None:
        # 예산 초과 시 [WARN] 예산 초과 N 으로 표시한다.
        with temp_budget_data_root() as paths:
            _seed_transaction(
                paths,
                Transaction(
                    id="t1",
                    type="expense",
                    date=date(2026, 5, 1),
                    amount=430000,
                    category="food",
                ),
            )
            BudgetRepository(path=paths.budgets).upsert(
                Budget(year_month="2026-05", amount=300000)
            )
            code, stdout, _ = _run_cli(
                [
                    "summary",
                    "-month",
                    "2026-05",
                    "-data-dir",
                    str(paths.root),
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("[WARN] 예산 초과 130,000", stdout)


class BudgetTests(unittest.TestCase):
    def test_budget_set_emits_ok_line(self) -> None:
        # budget set 은 [OK] 메시지와 함께 month/amount 컨텍스트를 출력한다.
        with temp_budget_data_root() as paths:
            code, stdout, _ = _run_cli(
                [
                    "budget",
                    "set",
                    "-month",
                    "2026-05",
                    "-amount",
                    "1000000",
                    "-data-dir",
                    str(paths.root),
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn(
                "[OK] 예산이 저장되었습니다. month=2026-05 amount=1,000,000",
                stdout,
            )


class CategoryTests(unittest.TestCase):
    def test_default_categories_listed_after_bootstrap(self) -> None:
        # 빈 데이터 디렉터리에서 category list 는 기본 4종을 보여준다.
        with temp_budget_data_root() as paths:
            code, stdout, _ = _run_cli(
                ["category", "list", "-data-dir", str(paths.root)]
            )
            self.assertEqual(code, 0)
            self.assertIn("- food", stdout)
            self.assertIn("- transport", stdout)
            self.assertIn("- rent", stdout)
            self.assertIn("- etc", stdout)
            self.assertIn("total: 4", stdout)

    def test_add_duplicate_category_warns_with_exit_zero(self) -> None:
        # 이미 존재하는 카테고리 추가는 [WARN] 으로 stderr 에만 표시되고 exit 0 이다.
        with temp_budget_data_root() as paths:
            code, stdout, stderr = _run_cli(
                [
                    "category",
                    "add",
                    "food",
                    "-data-dir",
                    str(paths.root),
                ]
            )
            self.assertEqual(code, 0)
            self.assertNotIn("[OK]", stdout)
            self.assertIn("[WARN] 이미 존재하는 카테고리입니다. name=food", stderr)

    def test_remove_in_use_blocks_with_error_and_hint(self) -> None:
        # 사용 중인 카테고리 삭제는 [ERROR] + 힌트 + exit 1 로 실패한다.
        with temp_budget_data_root() as paths:
            _seed_transaction(
                paths,
                Transaction(
                    id="t1",
                    type="expense",
                    date=date(2026, 5, 1),
                    amount=10,
                    category="food",
                ),
            )
            code, _, stderr = _run_cli(
                [
                    "category",
                    "remove",
                    "food",
                    "-data-dir",
                    str(paths.root),
                ]
            )
            self.assertEqual(code, 1)
            self.assertIn(
                "[ERROR] 사용 중인 카테고리는 삭제할 수 없습니다.", stderr
            )
            self.assertIn("name=food", stderr)
            self.assertIn("힌트: 해당 거래들의 카테고리를 먼저 변경하세요.", stderr)


class UpdateAndDeleteTests(unittest.TestCase):
    def _seed(self, paths) -> None:
        _seed_transaction(
            paths,
            Transaction(
                id="t000000000001",
                type="expense",
                date=date(2026, 5, 7),
                amount=12000,
                category="food",
                memo="lunch",
                tags=["a"],
            ),
        )

    def test_update_emits_ok_and_diff_lines(self) -> None:
        # 변경된 필드만 [INFO] field: old -> new 로 출력된다.
        with temp_budget_data_root() as paths:
            self._seed(paths)
            code, stdout, _ = _run_cli(
                [
                    "update",
                    "-id",
                    "t000000000001",
                    "-amount",
                    "13000",
                    "-memo",
                    "lunch (2)",
                    "-data-dir",
                    str(paths.root),
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("[OK] 거래가 수정되었습니다. id=t000000000001", stdout)
            self.assertIn("[INFO] amount: 12,000 -> 13,000", stdout)
            self.assertIn('[INFO] memo: "lunch" -> "lunch (2)"', stdout)

    def test_update_missing_id_exits_one_with_hint(self) -> None:
        # 존재하지 않는 id 는 NotFoundError 경로로 exit 1 을 만든다.
        with temp_budget_data_root() as paths:
            code, _, stderr = _run_cli(
                [
                    "update",
                    "-id",
                    "ghost",
                    "-amount",
                    "10",
                    "-data-dir",
                    str(paths.root),
                ]
            )
            self.assertEqual(code, 1)
            self.assertIn(
                "[ERROR] 해당 id 의 거래를 찾을 수 없습니다. id=ghost", stderr
            )
            self.assertIn("힌트: list 명령으로 id 를 확인하세요.", stderr)

    def test_delete_existing_id_succeeds(self) -> None:
        # 존재하는 id 삭제는 [OK] 메시지와 함께 exit 0.
        with temp_budget_data_root() as paths:
            self._seed(paths)
            code, stdout, _ = _run_cli(
                [
                    "delete",
                    "-id",
                    "t000000000001",
                    "-data-dir",
                    str(paths.root),
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("[OK] 거래가 삭제되었습니다. id=t000000000001", stdout)
            remaining = list(
                TransactionRepository(path=paths.transactions).iter_transactions()
            )
            self.assertEqual(remaining, [])

    def test_delete_missing_id_exits_one(self) -> None:
        # 존재하지 않는 id 삭제는 NotFoundError → exit 1 로 흐른다.
        with temp_budget_data_root() as paths:
            code, _, stderr = _run_cli(
                ["delete", "-id", "ghost", "-data-dir", str(paths.root)]
            )
            self.assertEqual(code, 1)
            self.assertIn(
                "[ERROR] 해당 id 의 거래를 찾을 수 없습니다.", stderr
            )


class AddInteractiveTests(unittest.TestCase):
    def test_shows_available_categories_before_category_prompt(self) -> None:
        # category 입력 전에 등록된 카테고리 목록을 안내한다.
        with temp_budget_data_root() as paths:
            inputs = [
                "2026-05-08",
                "expense",
                "food",
                "12000",
                "",
                "",
            ]
            code, stdout, _ = _run_cli(
                ["add", "-data-dir", str(paths.root)], inputs=inputs
            )
            self.assertEqual(code, 0)
            self.assertIn("[INFO] category options:", stdout)
            self.assertIn("food", stdout)
            self.assertIn("transport", stdout)
            self.assertIn("rent", stdout)
            self.assertIn("etc", stdout)

    def test_interactive_happy_path_creates_transaction(self) -> None:
        # 6개 입력을 모두 통과하면 [OK] 메시지 + id 가 출력되고 저장소에 1건 추가된다.
        with temp_budget_data_root() as paths:
            inputs = [
                "2026-05-08",
                "expense",
                "food",
                "12000",
                "lunch",
                "a,b",
            ]
            code, stdout, _ = _run_cli(
                ["add", "-data-dir", str(paths.root)], inputs=inputs
            )
            self.assertEqual(code, 0)
            self.assertIn("[OK] 거래가 저장되었습니다. id=", stdout)
            stored = list(
                TransactionRepository(path=paths.transactions).iter_transactions()
            )
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0].amount, 12000)
            self.assertEqual(stored[0].tags, ["a", "b"])

    def test_amount_re_prompts_on_invalid_value(self) -> None:
        # plan §9.1 에 따라 amount 음수 입력은 재요청되고, 양수가 들어오면 성공한다.
        with temp_budget_data_root() as paths:
            inputs = [
                "2026-05-08",
                "expense",
                "food",
                "-100",
                "12000",
                "",
                "",
            ]
            code, stdout, stderr = _run_cli(
                ["add", "-data-dir", str(paths.root)], inputs=inputs
            )
            self.assertEqual(code, 0)
            self.assertIn("[ERROR] amount 는 양수여야 합니다.", stderr)
            self.assertIn("힌트: 0 보다 큰 정수를 입력하세요.", stderr)
            self.assertIn("[OK] 거래가 저장되었습니다. id=", stdout)


class ImportTests(unittest.TestCase):
    def _write_csv(self, path, rows: list[list[str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as fp:
            writer = csv.writer(fp)
            for row in rows:
                writer.writerow(row)

    def test_partial_success_lists_skip_reasons(self) -> None:
        # 부분 성공 시 [OK] 메시지 + skip line 사유 나열.
        with temp_budget_data_root() as paths:
            source = paths.root / "in.csv"
            self._write_csv(
                source,
                [
                    list(EXPECTED_CSV_HEADER),
                    ["2026-05-01", "expense", "food", "12000", "ok", ""],
                    ["2026-05-02", "expense", "food", "-100", "neg", ""],
                ],
            )
            code, stdout, _ = _run_cli(
                [
                    "import",
                    "-from",
                    str(source),
                    "-data-dir",
                    str(paths.root),
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("[OK] CSV 가져오기 완료. 처리 2건 (성공 1, 스킵 1)", stdout)
            self.assertIn('- skip line 3: invalid amount "-100"', stdout)
            self.assertIn(f"file: {paths.transactions}", stdout)

    def test_total_failure_emits_error_and_exits_one(self) -> None:
        # 모든 행이 실패하면 plan §9.7 메시지로 exit 1.
        with temp_budget_data_root() as paths:
            source = paths.root / "in.csv"
            self._write_csv(
                source,
                [
                    list(EXPECTED_CSV_HEADER),
                    ["bad", "expense", "food", "100", "x", ""],
                ],
            )
            code, _, stderr = _run_cli(
                [
                    "import",
                    "-from",
                    str(source),
                    "-data-dir",
                    str(paths.root),
                ]
            )
            self.assertEqual(code, 1)
            self.assertIn(
                "[ERROR] CSV 가져오기에 실패했습니다.", stderr
            )
            self.assertIn(
                "헤더가 [date,type,category,amount,memo,tags] 인지", stderr
            )


class ExportTests(unittest.TestCase):
    def test_export_with_month_writes_filtered_rows(self) -> None:
        # -month 옵션으로 해당 월 거래만 CSV 로 기록되고 헤더가 plan §4.13 순서다.
        with temp_budget_data_root() as paths:
            for tx in (
                Transaction(
                    id="t1",
                    type="expense",
                    date=date(2026, 5, 1),
                    amount=10,
                    category="food",
                ),
                Transaction(
                    id="t2",
                    type="expense",
                    date=date(2026, 4, 30),
                    amount=20,
                    category="food",
                ),
            ):
                _seed_transaction(paths, tx)
            target = paths.root / "out.csv"
            code, stdout, _ = _run_cli(
                [
                    "export",
                    "-out",
                    str(target),
                    "-month",
                    "2026-05",
                    "-data-dir",
                    str(paths.root),
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("[OK] CSV 내보내기 완료. 처리 1건", stdout)
            with target.open("r", encoding="utf-8", newline="") as fp:
                rows = list(csv.reader(fp))
            self.assertEqual(rows[0], list(EXPECTED_CSV_HEADER))
            self.assertEqual(len(rows), 2)

    def test_export_missing_filters_exits_two(self) -> None:
        # -month 도 -from/-to 도 없으면 plan §9.7 메시지로 exit 2.
        with temp_budget_data_root() as paths:
            target = paths.root / "out.csv"
            code, _, stderr = _run_cli(
                [
                    "export",
                    "-out",
                    str(target),
                    "-data-dir",
                    str(paths.root),
                ]
            )
            self.assertEqual(code, 2)
            self.assertIn(
                "[ERROR] export 는 -month 또는 -from + -to 중 하나가 필수입니다.",
                stderr,
            )
            self.assertIn(
                "힌트: 예) export -out out.csv -month 2026-05", stderr
            )


if __name__ == "__main__":
    unittest.main()
