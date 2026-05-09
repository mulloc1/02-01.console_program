"""Tests for budget_app.services (plan.md §6, §11)."""

from __future__ import annotations

import unittest
from datetime import date

import helpers  # noqa: F401  side-effect: extends sys.path so budget_app imports

from budget_app.errors import (
    CategoryInUseError,
    NotFoundError,
    UserInputError,
)
from budget_app.main import DEFAULT_CATEGORIES, _bootstrap_default_categories
from budget_app.models import Budget, Category, Transaction
from budget_app.repositories import (
    BudgetRepository,
    CategoryRepository,
    TransactionRepository,
)
from budget_app.services import (
    add_category,
    add_transaction,
    delete_transaction,
    get_budget,
    list_transactions,
    remove_category,
    search_transactions,
    set_budget,
    summarize_month,
    update_transaction,
)
from budget_app.types import TransactionFilters
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


def _seed_transactions(
    repo: TransactionRepository, transactions: list[Transaction]
) -> None:
    for tx in transactions:
        repo.append(tx)


class AddTransactionTests(unittest.TestCase):
    def test_returns_persisted_transaction_with_generated_id(self) -> None:
        # add_transaction이 검증 통과 시 id를 부여해 저장하고 반환하는지 검증한다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            cat_repo = CategoryRepository(path=paths.categories)
            _seed_categories(cat_repo, ("food",))
            ids = _SequentialIds()
            created = add_transaction(
                tx_repo=tx_repo,
                cat_repo=cat_repo,
                type="expense",
                date_str="2026-05-08",
                category="food",
                amount=12000,
                memo="lunch",
                tags=["a", "b"],
                id_factory=ids,
            )
            expected = Transaction(
                id="id0001",
                type="expense",
                date=date(2026, 5, 8),
                amount=12000,
                category="food",
                memo="lunch",
                tags=["a", "b"],
            )
            self.assertEqual(created, expected)
            self.assertEqual(list(tx_repo.iter_transactions()), [expected])

    def test_invalid_date_raises_user_input_error(self) -> None:
        # 날짜 파싱 실패가 UserInputError로 변환되는지 검증한다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            cat_repo = CategoryRepository(path=paths.categories)
            _seed_categories(cat_repo, ("food",))
            with self.assertRaises(UserInputError) as ctx:
                add_transaction(
                    tx_repo=tx_repo,
                    cat_repo=cat_repo,
                    type="expense",
                    date_str="2026/05/08",
                    category="food",
                    amount=10,
                )
            self.assertEqual(ctx.exception.context.get("value"), "2026/05/08")

    def test_invalid_type_raises_user_input_error(self) -> None:
        # type이 income/expense 외의 값이면 UserInputError를 발생시키는지 검증한다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            cat_repo = CategoryRepository(path=paths.categories)
            _seed_categories(cat_repo, ("food",))
            with self.assertRaises(UserInputError):
                add_transaction(
                    tx_repo=tx_repo,
                    cat_repo=cat_repo,
                    type="transfer",
                    date_str="2026-05-08",
                    category="food",
                    amount=1,
                )

    def test_non_positive_amount_carries_hint(self) -> None:
        # amount<=0 검증 실패 시 plan §9.1 힌트가 예외에 포함되는지 검증한다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            cat_repo = CategoryRepository(path=paths.categories)
            _seed_categories(cat_repo, ("food",))
            with self.assertRaises(UserInputError) as ctx:
                add_transaction(
                    tx_repo=tx_repo,
                    cat_repo=cat_repo,
                    type="expense",
                    date_str="2026-05-08",
                    category="food",
                    amount=-100,
                )
            self.assertEqual(ctx.exception.context.get("value"), -100)
            self.assertIn("0 보다 큰 정수", ctx.exception.hint)

    def test_unknown_category_raises_user_input_error(self) -> None:
        # 등록되지 않은 카테고리는 UserInputError로 거부되는지 검증한다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            cat_repo = CategoryRepository(path=paths.categories)
            _seed_categories(cat_repo, ("food",))
            with self.assertRaises(UserInputError) as ctx:
                add_transaction(
                    tx_repo=tx_repo,
                    cat_repo=cat_repo,
                    type="expense",
                    date_str="2026-05-08",
                    category="travel",
                    amount=10,
                )
            self.assertEqual(ctx.exception.context.get("category"), "travel")


class ListTransactionsTests(unittest.TestCase):
    def test_returns_newest_first(self) -> None:
        # list_transactions가 date 내림차순으로 yield 하는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = TransactionRepository(path=paths.transactions)
            _seed_transactions(
                repo,
                [
                    Transaction("a", "expense", date(2026, 1, 1), 1, "x"),
                    Transaction("b", "expense", date(2026, 3, 1), 1, "x"),
                    Transaction("c", "expense", date(2026, 2, 1), 1, "x"),
                ],
            )
            self.assertEqual(
                [t.id for t in list_transactions(repo, limit=10)],
                ["b", "c", "a"],
            )

    def test_respects_limit(self) -> None:
        # 정렬 후 정확히 limit 건만 반환되는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = TransactionRepository(path=paths.transactions)
            _seed_transactions(
                repo,
                [
                    Transaction("a", "expense", date(2026, 1, 1), 1, "x"),
                    Transaction("b", "expense", date(2026, 3, 1), 1, "x"),
                    Transaction("c", "expense", date(2026, 2, 1), 1, "x"),
                ],
            )
            self.assertEqual(
                [t.id for t in list_transactions(repo, limit=2)],
                ["b", "c"],
            )

    def test_invalid_limit_raises(self) -> None:
        # 0 이하 limit이 UserInputError를 발생시키는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = TransactionRepository(path=paths.transactions)
            with self.assertRaises(UserInputError):
                list(list_transactions(repo, limit=0))


class SearchTransactionsTests(unittest.TestCase):
    def _build_repo(self, paths) -> TransactionRepository:
        repo = TransactionRepository(path=paths.transactions)
        _seed_transactions(
            repo,
            [
                Transaction(
                    "a",
                    "expense",
                    date(2026, 5, 1),
                    1000,
                    "food",
                    memo="brunch",
                    tags=["weekend"],
                ),
                Transaction(
                    "b",
                    "expense",
                    date(2026, 5, 5),
                    2000,
                    "transport",
                    memo="taxi",
                    tags=["work"],
                ),
                Transaction(
                    "c",
                    "income",
                    date(2026, 5, 25),
                    500_000,
                    "salary",
                    memo="payday",
                    tags=["work"],
                ),
                Transaction(
                    "d",
                    "expense",
                    date(2026, 4, 30),
                    8000,
                    "food",
                    memo="lunch",
                    tags=["team"],
                ),
            ],
        )
        return repo

    def test_combines_period_category_and_tag(self) -> None:
        # 기간 + 카테고리 + 태그 + 키워드 조합을 동시에 적용하는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = self._build_repo(paths)
            filters = TransactionFilters(
                from_date=date(2026, 5, 1),
                to_date=date(2026, 5, 31),
                type="expense",
                category="food",
                query="bru",
                tag="weekend",
            )
            self.assertEqual(
                [t.id for t in search_transactions(repo, filters)],
                ["a"],
            )

    def test_yields_newest_first(self) -> None:
        # search 결과도 최신순으로 정렬되는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = self._build_repo(paths)
            filters = TransactionFilters(type="expense")
            self.assertEqual(
                [t.id for t in search_transactions(repo, filters)],
                ["b", "a", "d"],
            )


class SummarizeMonthTests(unittest.TestCase):
    def test_aggregates_income_expense_balance_and_top_categories(self) -> None:
        # 일반 케이스에서 income/expense/balance 및 카테고리 TOP N이 계산되는지 검증한다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            budget_repo = BudgetRepository(path=paths.budgets)
            _seed_transactions(
                tx_repo,
                [
                    Transaction("a", "income", date(2026, 5, 25), 1_500_000, "salary"),
                    Transaction("b", "expense", date(2026, 5, 8), 180_000, "food"),
                    Transaction("c", "expense", date(2026, 5, 9), 120_000, "transport"),
                    Transaction("d", "expense", date(2026, 5, 10), 80_000, "rent"),
                    Transaction("e", "expense", date(2026, 5, 11), 50_000, "etc"),
                    Transaction("f", "expense", date(2026, 4, 30), 9_000, "food"),
                ],
            )
            summary = summarize_month(
                tx_repo=tx_repo,
                budget_repo=budget_repo,
                year_month="2026-05",
                top_n=3,
            )
            self.assertEqual(summary.income, 1_500_000)
            self.assertEqual(summary.expense, 430_000)
            self.assertEqual(summary.balance, 1_070_000)
            self.assertEqual(
                [(c.category, c.amount) for c in summary.top_categories],
                [("food", 180_000), ("transport", 120_000), ("rent", 80_000)],
            )
            self.assertIsNone(summary.budget_usage)
            self.assertFalse(summary.is_empty)

    def test_includes_budget_usage_when_set(self) -> None:
        # 예산이 설정된 달의 사용률과 초과 금액이 계산되는지 검증한다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            budget_repo = BudgetRepository(path=paths.budgets)
            budget_repo.upsert(Budget("2026-05", 300_000))
            _seed_transactions(
                tx_repo,
                [
                    Transaction("a", "expense", date(2026, 5, 8), 180_000, "food"),
                    Transaction("b", "expense", date(2026, 5, 9), 250_000, "rent"),
                ],
            )
            summary = summarize_month(
                tx_repo=tx_repo,
                budget_repo=budget_repo,
                year_month="2026-05",
                top_n=5,
            )
            self.assertIsNotNone(summary.budget_usage)
            usage = summary.budget_usage
            assert usage is not None  # type narrowing for mypy/pyright
            self.assertEqual(usage.limit, 300_000)
            self.assertEqual(usage.used, 430_000)
            self.assertEqual(usage.over_amount, 130_000)
            self.assertTrue(usage.is_over)

    def test_empty_month_marks_summary_empty(self) -> None:
        # 데이터가 없는 달은 is_empty=True로 표기되는지 검증한다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            budget_repo = BudgetRepository(path=paths.budgets)
            summary = summarize_month(
                tx_repo=tx_repo,
                budget_repo=budget_repo,
                year_month="2026-05",
                top_n=5,
            )
            self.assertEqual(summary.income, 0)
            self.assertEqual(summary.expense, 0)
            self.assertEqual(summary.balance, 0)
            self.assertEqual(summary.top_categories, [])
            self.assertTrue(summary.is_empty)

    def test_invalid_year_month_raises(self) -> None:
        # year_month 형식 위반이 UserInputError로 거부되는지 검증한다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            budget_repo = BudgetRepository(path=paths.budgets)
            with self.assertRaises(UserInputError):
                summarize_month(
                    tx_repo=tx_repo,
                    budget_repo=budget_repo,
                    year_month="2026/05",
                    top_n=5,
                )


class BudgetServiceTests(unittest.TestCase):
    def test_set_and_get_round_trip(self) -> None:
        # set_budget / get_budget 라운드트립을 검증한다.
        with temp_budget_data_root() as paths:
            repo = BudgetRepository(path=paths.budgets)
            saved = set_budget(repo, "2026-05", 1_000_000)
            self.assertEqual(saved, Budget("2026-05", 1_000_000))
            self.assertEqual(get_budget(repo, "2026-05"), saved)

    def test_set_replaces_existing_year_month(self) -> None:
        # 같은 month로 다시 set_budget하면 한 row만 유지하면서 갱신되는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = BudgetRepository(path=paths.budgets)
            set_budget(repo, "2026-05", 1_000_000)
            set_budget(repo, "2026-05", 1_500_000)
            self.assertEqual(
                list(repo.iter_budgets()),
                [Budget("2026-05", 1_500_000)],
            )

    def test_get_returns_none_when_missing(self) -> None:
        # 저장된 적 없는 month는 get_budget이 None을 반환하는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = BudgetRepository(path=paths.budgets)
            self.assertIsNone(get_budget(repo, "2026-05"))

    def test_invalid_amount_raises(self) -> None:
        # 0/음수 amount는 UserInputError로 거부되는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = BudgetRepository(path=paths.budgets)
            with self.assertRaises(UserInputError):
                set_budget(repo, "2026-05", 0)


class CategoryServiceTests(unittest.TestCase):
    def test_add_category(self) -> None:
        # add_category가 새 카테고리를 저장하고 반환하는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = CategoryRepository(path=paths.categories)
            created = add_category(repo, "salary")
            self.assertEqual(created, Category("salary"))
            self.assertEqual(
                [c.name for c in repo.iter_categories()],
                ["salary"],
            )

    def test_add_duplicate_raises(self) -> None:
        # 동일 이름의 카테고리 추가 시 UserInputError로 거부되는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = CategoryRepository(path=paths.categories)
            add_category(repo, "salary")
            with self.assertRaises(UserInputError):
                add_category(repo, "salary")

    def test_add_blank_raises(self) -> None:
        # 공백/빈 이름은 UserInputError로 거부되는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = CategoryRepository(path=paths.categories)
            with self.assertRaises(UserInputError):
                add_category(repo, "   ")

    def test_remove_unused_category(self) -> None:
        # 사용 중이 아닌 카테고리는 정상적으로 삭제되는지 검증한다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            cat_repo = CategoryRepository(path=paths.categories)
            _seed_categories(cat_repo, ("food", "etc"))
            remove_category(tx_repo=tx_repo, cat_repo=cat_repo, name="etc")
            self.assertEqual(
                [c.name for c in cat_repo.iter_categories()],
                ["food"],
            )

    def test_remove_in_use_raises_with_count(self) -> None:
        # 사용 중인 카테고리 삭제 시 사용 건수가 컨텍스트에 포함되는지 검증한다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            cat_repo = CategoryRepository(path=paths.categories)
            _seed_categories(cat_repo, ("food",))
            _seed_transactions(
                tx_repo,
                [
                    Transaction("a", "expense", date(2026, 5, 1), 1, "food"),
                    Transaction("b", "expense", date(2026, 5, 2), 1, "food"),
                ],
            )
            with self.assertRaises(CategoryInUseError) as ctx:
                remove_category(tx_repo=tx_repo, cat_repo=cat_repo, name="food")
            self.assertEqual(ctx.exception.context.get("name"), "food")
            self.assertEqual(ctx.exception.context.get("in_use"), 2)

    def test_remove_unknown_raises_not_found(self) -> None:
        # 존재하지 않는 카테고리 삭제는 NotFoundError로 처리되는지 검증한다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            cat_repo = CategoryRepository(path=paths.categories)
            with self.assertRaises(NotFoundError):
                remove_category(
                    tx_repo=tx_repo, cat_repo=cat_repo, name="missing"
                )

    def test_bootstrap_seeds_when_empty(self) -> None:
        # 빈 카테고리 저장소에 기본 카테고리 4종이 시드되는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = CategoryRepository(path=paths.categories)
            _bootstrap_default_categories(repo)
            self.assertEqual(
                [c.name for c in repo.iter_categories()],
                list(DEFAULT_CATEGORIES),
            )

    def test_bootstrap_no_op_when_existing(self) -> None:
        # 이미 카테고리가 있으면 bootstrap이 아무것도 하지 않는지 검증한다.
        with temp_budget_data_root() as paths:
            repo = CategoryRepository(path=paths.categories)
            repo.append(Category("custom"))
            _bootstrap_default_categories(repo)
            self.assertEqual(
                [c.name for c in repo.iter_categories()],
                ["custom"],
            )


class UpdateTransactionTests(unittest.TestCase):
    def _seed(self, paths) -> tuple[TransactionRepository, CategoryRepository]:
        tx_repo = TransactionRepository(path=paths.transactions)
        cat_repo = CategoryRepository(path=paths.categories)
        _seed_categories(cat_repo, ("food", "rent"))
        _seed_transactions(
            tx_repo,
            [
                Transaction(
                    id="t0001",
                    type="expense",
                    date=date(2026, 5, 1),
                    amount=12000,
                    category="food",
                    memo="lunch",
                    tags=["a"],
                ),
                Transaction(
                    id="t0002",
                    type="income",
                    date=date(2026, 5, 2),
                    amount=500000,
                    category="rent",
                    memo="salary",
                    tags=[],
                ),
            ],
        )
        return tx_repo, cat_repo

    def test_updates_only_supplied_fields(self) -> None:
        # 제공된 필드만 변경되고 나머지는 보존되며 (before, after) 가 반환된다.
        with temp_budget_data_root() as paths:
            tx_repo, cat_repo = self._seed(paths)
            before, after = update_transaction(
                tx_repo=tx_repo,
                cat_repo=cat_repo,
                id="t0001",
                amount=13000,
                memo="lunch (2)",
            )
            self.assertEqual(before.amount, 12000)
            self.assertEqual(after.amount, 13000)
            self.assertEqual(after.memo, "lunch (2)")
            self.assertEqual(after.category, "food")
            self.assertEqual(after.date, date(2026, 5, 1))
            stored = {tx.id: tx for tx in tx_repo.iter_transactions()}
            self.assertEqual(stored["t0001"], after)
            self.assertEqual(stored["t0002"].amount, 500000)

    def test_updates_multiple_fields_atomically(self) -> None:
        # 여러 필드 동시 변경이 한 번의 replace_all 로 영속화된다.
        with temp_budget_data_root() as paths:
            tx_repo, cat_repo = self._seed(paths)
            _, after = update_transaction(
                tx_repo=tx_repo,
                cat_repo=cat_repo,
                id="t0001",
                date_str="2026-06-01",
                category="rent",
                tags=["b", "c"],
            )
            self.assertEqual(after.date, date(2026, 6, 1))
            self.assertEqual(after.category, "rent")
            self.assertEqual(after.tags, ["b", "c"])

    def test_missing_id_raises_not_found(self) -> None:
        # 존재하지 않는 id 는 NotFoundError + id 컨텍스트로 보고된다.
        with temp_budget_data_root() as paths:
            tx_repo, cat_repo = self._seed(paths)
            with self.assertRaises(NotFoundError) as ctx:
                update_transaction(
                    tx_repo=tx_repo,
                    cat_repo=cat_repo,
                    id="ghost",
                    amount=1,
                )
            self.assertEqual(ctx.exception.context.get("id"), "ghost")

    def test_invalid_amount_raises_user_input_error(self) -> None:
        # 양수가 아닌 amount 는 UserInputError 로 거부되고 저장이 변경되지 않는다.
        with temp_budget_data_root() as paths:
            tx_repo, cat_repo = self._seed(paths)
            with self.assertRaises(UserInputError):
                update_transaction(
                    tx_repo=tx_repo,
                    cat_repo=cat_repo,
                    id="t0001",
                    amount=-1,
                )
            stored = {tx.id: tx for tx in tx_repo.iter_transactions()}
            self.assertEqual(stored["t0001"].amount, 12000)

    def test_unknown_category_raises_user_input_error(self) -> None:
        # 등록되지 않은 카테고리로의 변경은 거부된다.
        with temp_budget_data_root() as paths:
            tx_repo, cat_repo = self._seed(paths)
            with self.assertRaises(UserInputError):
                update_transaction(
                    tx_repo=tx_repo,
                    cat_repo=cat_repo,
                    id="t0001",
                    category="ghost",
                )

    def test_invalid_type_raises_user_input_error(self) -> None:
        # 허용되지 않는 type 은 UserInputError 로 거부된다.
        with temp_budget_data_root() as paths:
            tx_repo, cat_repo = self._seed(paths)
            with self.assertRaises(UserInputError):
                update_transaction(
                    tx_repo=tx_repo,
                    cat_repo=cat_repo,
                    id="t0001",
                    type="BAD",
                )


class DeleteTransactionTests(unittest.TestCase):
    def test_removes_only_target_row(self) -> None:
        # 대상 거래만 삭제되고 다른 거래는 그대로 유지된다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            _seed_transactions(
                tx_repo,
                [
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
                        date=date(2026, 5, 2),
                        amount=20,
                        category="food",
                    ),
                ],
            )
            removed = delete_transaction(tx_repo=tx_repo, id="t1")
            self.assertEqual(removed.id, "t1")
            remaining = [tx.id for tx in tx_repo.iter_transactions()]
            self.assertEqual(remaining, ["t2"])

    def test_missing_id_raises_not_found(self) -> None:
        # 존재하지 않는 id 삭제는 NotFoundError 로 보고된다.
        with temp_budget_data_root() as paths:
            tx_repo = TransactionRepository(path=paths.transactions)
            with self.assertRaises(NotFoundError) as ctx:
                delete_transaction(tx_repo=tx_repo, id="ghost")
            self.assertEqual(ctx.exception.context.get("id"), "ghost")


if __name__ == "__main__":
    unittest.main()
