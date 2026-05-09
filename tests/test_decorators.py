"""Tests for budget_app.decorators (plan.md §7, §9)."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr

import helpers  # noqa: F401  side-effect: extends sys.path so budget_app imports

from budget_app.decorators import (
    measure_time,
    translate_errors,
)
from budget_app.errors import (
    CategoryInUseError,
    NotFoundError,
    UserInputError,
)


class TranslateErrorsTests(unittest.TestCase):
    def test_user_input_error_exits_with_code_two(self) -> None:
        # UserInputError가 [ERROR]+힌트 출력과 종료 코드 2로 변환되는지 검증한다.
        @translate_errors
        def boom() -> None:
            raise UserInputError(
                "amount 는 양수여야 합니다.",
                value=-100,
                hint="0 보다 큰 정수를 입력하세요.",
            )

        buf = io.StringIO()
        with redirect_stderr(buf):
            with self.assertRaises(SystemExit) as ctx:
                boom()
        self.assertEqual(ctx.exception.code, 2)
        text = buf.getvalue()
        self.assertIn("[ERROR] amount 는 양수여야 합니다. value=-100", text)
        self.assertIn("힌트: 0 보다 큰 정수를 입력하세요.", text)

    def test_category_in_use_error_exits_with_code_one(self) -> None:
        # 운영 오류는 종료 코드 1과 기본 힌트가 적용되는지 검증한다.
        @translate_errors
        def boom() -> None:
            raise CategoryInUseError(
                "사용 중인 카테고리는 삭제할 수 없습니다.",
                name="food",
                in_use=12,
            )

        buf = io.StringIO()
        with redirect_stderr(buf):
            with self.assertRaises(SystemExit) as ctx:
                boom()
        self.assertEqual(ctx.exception.code, 1)
        text = buf.getvalue()
        self.assertIn("name=food in_use=12", text)
        self.assertIn("힌트: 해당 거래들의 카테고리를 먼저 변경하세요.", text)

    def test_not_found_uses_default_hint(self) -> None:
        # NotFoundError가 기본 힌트("list 명령으로 ...")로 출력되는지 검증한다.
        @translate_errors
        def boom() -> None:
            raise NotFoundError("해당 id 의 거래를 찾을 수 없습니다.", id="zzzz")

        buf = io.StringIO()
        with redirect_stderr(buf):
            with self.assertRaises(SystemExit):
                boom()
        self.assertIn("힌트: list 명령으로 id 를 확인하세요.", buf.getvalue())

    def test_passes_through_non_domain_errors(self) -> None:
        # 도메인 예외가 아닌 일반 예외는 그대로 전파되는지 검증한다.
        @translate_errors
        def boom() -> None:
            raise RuntimeError("unexpected")

        with self.assertRaises(RuntimeError):
            boom()


class MeasureTimeTests(unittest.TestCase):
    def test_silent_when_not_verbose(self) -> None:
        # verbose 플래그가 없을 때 stderr 출력이 없어야 함을 검증한다.
        @measure_time
        def handler() -> int:
            return 7

        buf = io.StringIO()
        with redirect_stderr(buf):
            result = handler()
        self.assertEqual(result, 7)
        self.assertEqual(buf.getvalue(), "")

    def test_logs_elapsed_when_verbose_kwarg(self) -> None:
        # verbose=True 인자를 받으면 elapsed 라인이 stderr에 출력되는지 검증한다.
        @measure_time
        def handler() -> bool:
            return True

        buf = io.StringIO()
        with redirect_stderr(buf):
            handler(verbose=True)
        self.assertIn("[INFO] handler elapsed=", buf.getvalue())
        self.assertIn("ms", buf.getvalue())

if __name__ == "__main__":
    unittest.main()
