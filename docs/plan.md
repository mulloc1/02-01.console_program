# 콘솔 가계부 구현 계획 (plan.md)

본 문서는 `docs/subject.md` 의 요구사항과 레포지토리 `.cursorrules` 의 코딩/구조 규칙을 동시에 만족하는 단계별 구현 계획이다. 「Minimal-First / YAGNI」 원칙(.cursorrules §3)에 따라 **요구사항을 만족하는 최소 구성**으로 시작하고, 보너스 과제는 본 과제 완료 이후 별도 단계로 분리한다.

---

## 1. 목표 요약

- Python 3.14 기준 콘솔 가계부 애플리케이션을 **단일 패키지**(`budget_app`)로 구현한다.
- 실행 진입점은 `python -m budget_app <command> [options]` 로 통일한다(subject §4.1).
- 데이터는 파일 기반(JSONL)으로 영구 저장하며, 읽기는 **제너레이터 스트리밍**으로만 처리한다(subject §4.7, §4.9).
- 공통 관심사(예외/로그/시간 측정)는 **데코레이터**로 분리한다(subject §4.14).
- 모든 함수 시그니처에 **타입 힌트**를 적용한다(.cursorrules §4 Type Hinting).

---

## 2. 사전 고정 결정 (Locked Decisions)

subject 가 「안 A / 안 B」 중 하나를 문서에 고정하라고 명시한 항목과, 그 외 본 과제 범위에서 미리 굳혀둘 결정.


| 항목                            | 결정                                                                       | 근거                                       |
| ----------------------------- | ------------------------------------------------------------------------ | ---------------------------------------- |
| 저장 포맷 (subject §4.4)          | **JSONL**                                                                | 라인 단위 스트리밍 친화적, `json` 표준 라이브러리만으로 처리 가능 |
| 카테고리 초기 동작 (subject §4.5)     | **안 A · 기본 카테고리 자동 생성** (`food`, `transport`, `rent`, `etc`)             | 첫 실행 UX 개선, `add` 즉시 사용 가능               |
| `update` 입력 방식 (subject §4.8) | **안 A · 옵션 기반** (`update -id <id> [-date …] …`)                            | 자동화/스크립트 친화, CLI 일관성                     |
| 데이터 디렉터리                      | 기본 `./data` (옵션 `-data-dir <path>` 로 변경)                                 | subject §4.4 권장값                         |
| 옵션 표기                         | 모두 단일 `-` (`-help`, `-limit`, `-from`, `-to`, `-month`)                  | subject §4.1                             |
| 테스트 러너                        | 표준 `unittest` (`python -m unittest discover -s tests -p 'test_*.py' -v`) | .cursorrules §5 Stdlib Test Runner       |


---

## 3. 디렉터리 / 모듈 구성

subject §4.16 ‘CLI / 서비스 / 저장소 / 모델’ 권장 분리를 따른다. .cursorrules §3 에 따라 **하위 디렉터리는 만들지 않고 단일 패키지 안에 평탄(flat)** 하게 둔다(증거 후 분리). `src/` ↔ `tests/` 구조 미러링 규칙(.cursorrules §5)도 단일 레벨에서 자연스럽게 만족된다.

```
02-1.console_program/
├── README.md                        # 실행법 / 저장 위치·형식 / CSV 스키마 / 명령 예시
├── docs/
│   ├── subject.md
│   └── plan.md                      # (본 문서)
├── pytest.ini                       # pythonpath = src, tests
├── budget_app/
│   ├── __init__.py
│   ├── __main__.py                  # python -m budget_app 진입점
│   ├── cli.py                       # 인자 파싱(argparse) · 명령 디스패치
│   ├── models.py                    # Transaction / Category / Budget (dataclass)
│   ├── decorators.py                # 예외/시간 측정 데코레이터
│   ├── repositories.py              # JSONL I/O, 제너레이터 스트리밍, 원자적 교체
│   ├── services.py                  # 검증·요약·예산 등 비즈니스 규칙
│   └── errors.py                    # 도메인 예외 (UserInputError 등)
└── tests/
    ├── helpers.py                   # 임시 데이터 디렉터리·서비스 조립 픽스처
    ├── test_models.py
    ├── test_decorators.py
    ├── test_repositories.py
    ├── test_services.py
    └── test_cli.py
```

- **클래스 수 요건(subject §4.2 ‘최소 2개’)**: `Transaction`, `Category`, `Budget` (dataclass) + `TransactionRepository`, `CategoryRepository`, `BudgetRepository` + `BudgetService` 등으로 충분히 만족.
- **모듈 수 요건(subject §4.16 ‘최소 3개’)**: `cli`, `services`, `repositories`, `models`, `decorators` 로 만족.

---

## 4. 데이터 모델 (`models.py`)

`@dataclass` 로 정의하고 모든 필드에 타입 힌트를 부여한다(.cursorrules §4 Type Hinting).


| 클래스           | 필드                                                                                                                                                              | 비고                                 |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| `Transaction` | `id: str`, `type: Literal["income","expense"]`, `date: date`, `amount: int`, `category: str`, `memo: str = ""`, `tags: list[str] = field(default_factory=list)` | `id` 는 `uuid4().hex[:12]` 등 짧은 식별자 |
| `Category`    | `name: str`                                                                                                                                                     | 단일 식별자                             |
| `Budget`      | `month: str` (`YYYY-MM`), `amount: int`                                                                                                                         | 월별 1건                              |


직렬화/역직렬화 헬퍼는 각 dataclass 모듈 내부에 두고, 외부에는 `to_dict()` / `from_dict()` 만 노출한다.

---

## 5. 저장 정책 (`repositories.py`)


| 파일                        | 포맷    | 1줄 스키마                                                                                                |
| ------------------------- | ----- | ----------------------------------------------------------------------------------------------------- |
| `data/transactions.jsonl` | JSONL | `{"id":..., "type":..., "date":"YYYY-MM-DD", "amount":..., "category":..., "memo":..., "tags":[...]}` |
| `data/categories.jsonl`   | JSONL | `{"name": "food"}`                                                                                    |
| `data/budgets.jsonl`      | JSONL | `{"month":"YYYY-MM", "amount": 500000}` (월별 1줄, 갱신 시 전체 재작성)                                          |


**핵심 원칙**

- `iter_transactions() -> Iterator[Transaction]` 처럼 **반드시 `yield` 기반 제너레이터로만 읽기**(subject §4.7).
- `update`/`delete` 는 **임시 파일에 쓰고 `os.replace` 로 교체**(subject §4.8 “원자적 교체 권장”, 보너스 §5 ‘저장 원자성 강화’의 핵심만 본 과제에 포함).
- 파일이 없으면 빈 파일을 자동 생성(subject §4.5).
- I/O 함수는 `pathlib.Path` 와 `Iterable[Transaction]` 등 추상 시그니처로 받아 테스트에서 임시 디렉터리를 주입할 수 있게 한다(.cursorrules §5 Testing Determinism).

---

## 6. 비즈니스 규칙 (`services.py`)


| 서비스/함수                                            | 책임                                             |
| ------------------------------------------------- | ---------------------------------------------- |
| `add_transaction()`                               | 입력 검증(날짜·금액·type·등록 카테고리) → 저장                 |
| `list_transactions(limit)`                        | 제너레이터 → 최신순 정렬 → 상위 `limit`                    |
| `search_transactions(filters)`                    | 제너레이터 파이프라인(필터링 후 최신순)                         |
| `summarize_month(month, top_n)`                   | 총수입/총지출/잔액 + 카테고리별 지출 TOP N + 예산 사용률           |
| `set_budget(month, amount)` / `get_budget(month)` | 예산 CRUD                                        |
| `add_category` / `remove_category`                | 사용 중 카테고리 삭제 차단(또는 대체 카테고리 요구) (subject §4.12) |
| `import_csv(path)` / `export_csv(path, filters)`  | UTF-8 헤더 포함, subject §4.13 스키마 고정              |


서비스 함수는 **순수 로직**으로 두고 I/O 는 인자로 받은 repository 에 위임한다(.cursorrules §4 SRP).

---

## 7. 데코레이터 (`decorators.py`)

subject §4.14 “1개 이상 구현·적용”을 만족하기 위해 다음을 둔다.

1. `@translate_errors` — 도메인 예외(`UserInputError`, `NotFoundError`)를 **원인 + 해결 힌트** 메시지로 변환하고 비-0 종료 코드를 유도(subject §4.15).
2. `@measure_time` — 옵션 `-verbose` 시에만 stderr 로 실행 시간 출력.

`cli.py` 의 명령 핸들러에 적용해 “실제 사용”을 보장한다.

---

## 8. CLI 명세 (`cli.py`)

- `argparse` 의 서브커맨드(`subparsers`)를 사용한다.
- 모든 옵션은 단일 `-` 로 통일(subject §4.1 옵션 표기). `argparse` 기본은 `--` 이므로 `add_argument("-month", ...)` 처럼 명시적으로 단일 하이픈을 등록한다.
- 명령별 인자 표:


| 명령           | 주요 인자                                                         | 비고                 |
| ------------ | ------------------------------------------------------------- | ------------------ |
| `add`        | (대화형)                                                         | `input()` 으로 순차 수집 |
| `list`       | `-limit N` (기본 20)                                            | 제너레이터 스트리밍         |
| `search`     | `-from`, `-to`, `-category`, `-type`, `-q`, `-tag`            |                    |
| `summary`    | `-month YYYY-MM`, `-top N` (기본 5)                             | 데이터 없는 달 메시지       |
| `budget set` | `-month`, `-amount`                                           |                    |
| `category`   | `add` / `list` / `remove`                                     | 사용 중 카테고리 삭제 정책 적용 |
| `update`     | `-id` 와 `-date`/`-type`/`-category`/`-amount`/`-memo`/`-tags` | **안 A 옵션 기반 고정**   |
| `delete`     | `-id <id>`                                                    | 없는 id 메시지          |
| `import`     | `-from <csv>`                                                 |                    |
| `export`     | `-out <csv>` + (`-month` 또는 `-from`+`-to`)                    |                    |
| (전역)         | `-data-dir <path>`, `-help`                                   |                    |


종료 코드: 정상 `0`, 입력 검증 실패 `2`, 그 외 오류 `1`.

---

## 9. 출력 화면 양식 (Output Specification)

subject §2.1 의 “출력·화면” 칸을 **stdout/stderr 단위까지 고정**한 사양이다. 모든 사용자용 메시지는 `[OK]` / `[INFO]` / `[WARN]` / `[ERROR]` 4 종 접두사로 통일하고, 데이터 행은 공백 정렬 테이블만 사용한다(외부 라이브러리 금지). 테스트(§11)는 본 절의 문자열을 기준으로 stdout/stderr 를 캡처해 검증한다.

> 표기 규약: 금액은 **천 단위 콤마**, 날짜는 `YYYY-MM-DD`, `id` 는 12자 16진수.

### 9.1 add — 거래 추가 (subject §4.6)

프롬프트(검증 실패 시 같은 항목을 다시 묻는다, subject §4.3):

```
date (YYYY-MM-DD): 2026-05-08
type (income/expense): expense
category: food
amount: 12000
memo (optional): 점심
tags (comma separated, optional): lunch,team
```

성공:

```
[OK] 거래가 저장되었습니다. id=a1b2c3d4e5f6
```

검증 실패 예 (`amount <= 0`):

```
[ERROR] amount 는 양수여야 합니다. value=-100
힌트: 0 보다 큰 정수를 입력하세요.
```

### 9.2 list / search — 목록·검색 (subject §4.7, §4.9)

동일 테이블 양식, **date 내림차순**(최신순), 제너레이터 스트리밍.

```
date        type     amount   category    id            memo
----------  -------  -------  ----------  ------------  ----------------
2026-05-07  expense   12,000  food        a1b2c3d4e5f6  점심
2026-05-06  income   500,000  salary      0987abcd1234  월급
total: 2 (limit=20)
```

`list` 데이터 없음:

```
거래 내역이 없습니다.
```

`search` 결과 없음:

```
조건에 맞는 거래가 없습니다.
```

### 9.3 summary — 월별 요약 (subject §4.10, §4.11)

기본:

```
[Summary] 2026-05
income:    1,500,000
expense:     430,000
balance:   1,070,000

[Top expenses by category] (TOP 5)
1. food        180,000 (41.9%)
2. transport   120,000 (27.9%)
3. rent         80,000 (18.6%)
4. etc          50,000 (11.6%)
```

예산이 설정된 경우 한 줄 추가:

```
[Budget] limit 1,000,000 / used 430,000 (43.0%) [OK]
```

예산 초과 시:

```
[Budget] limit 300,000 / used 430,000 (143.3%) [WARN] 예산 초과 130,000
```

해당 월 데이터 없음(subject §4.10 “데이터 없음” 명확 출력):

```
[Summary] 2026-05 - 데이터 없음
```

### 9.4 budget set — 예산 설정 (subject §4.11)

```
[OK] 예산이 저장되었습니다. month=2026-05 amount=1,000,000
```

### 9.5 category — 카테고리 관리 (subject §4.12)

`category list`:

```
- food
- transport
- rent
- etc
total: 4
```

`category add <name>` 성공 / 중복:

```
[OK] 카테고리가 추가되었습니다. name=salary
```

```
[WARN] 이미 존재하는 카테고리입니다. name=salary
```

`category remove <name>` 성공 / 사용 중(1차 정책 = 차단, §12 위험 표 참조):

```
[OK] 카테고리가 삭제되었습니다. name=etc
```

```
[ERROR] 사용 중인 카테고리는 삭제할 수 없습니다. name=food, in_use=12
힌트: 해당 거래들의 카테고리를 먼저 변경하세요.
```

### 9.6 update / delete — 수정·삭제 (subject §4.8)

`update` 성공(변경된 필드만 한 줄씩):

```
[OK] 거래가 수정되었습니다. id=a1b2c3d4e5f6
[INFO] amount: 12,000 -> 13,000
[INFO] memo: "점심" -> "점심(2)"
```

`delete` 성공:

```
[OK] 거래가 삭제되었습니다. id=a1b2c3d4e5f6
```

존재하지 않는 `id`(update / delete 공통):

```
[ERROR] 해당 id 의 거래를 찾을 수 없습니다. id=zzzz
힌트: list 명령으로 id 를 확인하세요.
```

### 9.7 import / export — CSV 입출력 (subject §4.13)

`import -from <csv>` 부분 성공(스킵 라인은 사유와 함께 나열):

```
[OK] CSV 가져오기 완료. 처리 13건 (성공 12, 스킵 1)
- skip line 7: invalid amount "-100"
file: ./data/transactions.jsonl
```

전부 실패:

```
[ERROR] CSV 가져오기에 실패했습니다. file=./in.csv
힌트: 헤더가 [date,type,category,amount,memo,tags] 인지, 인코딩이 UTF-8 인지 확인하세요.
```

`export -out <csv>` 성공:

```
[OK] CSV 내보내기 완료. 처리 27건
file: ./out/2026-05.csv
```

`export` 조건 누락(둘 중 하나 필수, subject §4.13):

```
[ERROR] export 는 -month 또는 -from + -to 중 하나가 필수입니다.
힌트: 예) export -out out.csv -month 2026-05
```

### 9.8 도움말 · 공통 오류 · 종료 코드 (subject §4.1, §4.15)

- `<command> -help` 는 argparse 표준 도움말을 그대로 출력(옵션 prefix `-` 통일).
- 처리되지 않은 예외도 스택트레이스 대신 `[ERROR]` + 힌트 한 줄로 변환한다(`@translate_errors`, §7).
- 종료 코드: 정상 `0`, 입력 검증 실패 `2`, 그 외 운영 오류 `1`.

### 9.9 출력 채널 정책


| 채널         | 용도                                                                         |
| ---------- | -------------------------------------------------------------------------- |
| **stdout** | 사용자 결과(테이블, `[OK]`, `[INFO]` 본문)                                           |
| **stderr** | `[WARN]`, `[ERROR]`, 데코레이터 진단 로그(`@measure_time -verbose`)                 |


테스트는 stdout/stderr 를 분리 캡처하여 본 절의 문자열과 대조한다(.cursorrules §5 Testing Determinism).

---

## 10. 단계별 구현 계획 (Phases)

각 단계는 **하나의 논리적 변경 = 한 커밋**(.cursorrules §5 Logical Commit Unit) 단위로 진행하고 Conventional Commits 접두사를 사용한다.

### Phase 0 — 프로젝트 스캐폴딩

- `budget_app/__init__.py`, `__main__.py` 만 둔 빈 패키지 생성.
- `pytest.ini` 에 `pythonpath = src` 등 설정(.cursorrules §5 ‘pytest 호환’).
- `tests/helpers.py` 에 임시 디렉터리·repository 팩토리.
- 커밋: `chore: scaffold budget_app package and test layout`

### Phase 1 — 모델 / 저장소 (CRUD 기반)

- `models.py` (`Transaction`, `Category`, `Budget`).
- `repositories.py` 에 JSONL 읽기 제너레이터 + append + 원자적 재작성.
- 테스트: `test_models.py`, `test_repositories.py`(임시 디렉터리, 라운드트립).
- 커밋: `feat: add jsonl repositories with streaming reads`

### Phase 2 — 비즈니스 로직 + 데코레이터

- `services.py` (검증, 요약, 예산 사용률).
- `decorators.py` (`translate_errors`, `measure_time`).
- `errors.py` (도메인 예외).
- 테스트: `test_services.py`, `test_decorators.py`.
- **`import_csv` / `export_csv`(subject §4.13)는 Phase 2.5 로 분리**해 구현량을 나눈다.
- 커밋: `feat: add transaction services and shared decorators`

### Phase 2.5 — CSV 가져오기·내보내기

- 목적: §6 표의 파일 I/O가 큰 블록을 Phase 3 CLI 전에 닫기 위해 **`import_csv` / `export_csv`만 별 단계로 구현**.
- `services.py` 확장 또는 동일 패키지 내 보조 함수(예: `_csv_helpers`)로 두되, **CLI·출력 문자열(plan §9.7)** 은 여전히 Phase 3 책임.
- 요구 요약(subject §4.13):
  - **UTF-8**, **헤더 포함**, 스키마 고정 `[date,type,category,amount,memo,tags]`.
  - `import`: 등록 카테고리·양수 금액·필수 컬럼 검증, 부분 성공 시 스킵 라인 사유 기록(§9.7).
  - `export`: `-month` **또는** `-from` + `-to` 조건에 맞는 거래만 스트리밍으로 기록(대량 대비).
- 테스트: `test_services.py`에 CSV 전용 케이스 추가하거나 `test_csv_io.py` 로 분리(임시 디렉터리·인코딩·스킵/성공 건수).
- 커밋: `feat: add csv import and export services`

### Phase 3 — CLI 통합

- `cli.py` 서브커맨드 구성(단일 `-` 옵션), `__main__.py` 연결.
- `add` 대화형, `list/search/summary/budget/category/update/delete/import/export` 옵션 인자.
- 테스트: `test_cli.py`(`subprocess` 또는 `cli.main([...])` 직접 호출, stdin/stdout 캡처).
- 커밋: `feat: wire cli subcommands for budget_app`

### Phase 4 — README · 문서 정리

- `README.md` 작성: 실행법, `./data` 위치, JSONL/CSV 스키마, 명령 예시(subject §2.2).
- `docs/plan.md` 의 “고정 결정” 표를 README 에 동기화.
- 커밋: `docs: add README with usage and schema`

### Phase 5 (선택) — 보너스 과제

- 본 과제 통과 후에만 별도 브랜치/커밋으로 진행한다(.cursorrules §3 YAGNI).
- 후보: `backup`, 반복 내역, 출력 정렬. 도입 시 본 plan 에 후속 결정 표를 추가한다.

---

## 11. 테스트 전략

- 러너: `python -m unittest discover -s tests -p 'test_*.py' -v` (.cursorrules §5).
- 결정성: 모든 테스트는 `tempfile.TemporaryDirectory()` 기반(.cursorrules §5 Testing Determinism). 시계 의존 코드는 `clock: Callable[[], date]` 주입.
- 단언: `self.assertEqual` 등 `assert`* 메서드만 합격 판정에 사용(.cursorrules §5 Assert First).
- 각 테스트 함수 첫 줄에 **검증 목적 한 줄 주석**(.cursorrules §5 Test Purpose Comments).
- 공통 픽스처는 `tests/helpers.py` 한 곳에 모은다.

핵심 케이스 체크리스트:

- `Transaction.from_dict` 라운드트립.
- 빈 파일 / 손상된 라인 처리(스트리밍 중 1줄 오류로 전체 실패하지 않도록 정책 결정).
- `list -limit` 정확히 N건.
- `search` 필터 조합(기간 + 카테고리 + 키워드).
- `summary` 데이터 없는 달 → 명시적 “데이터 없음”.
- `budget` 사용률·초과 경고.
- `category remove` 사용 중일 때 차단.
- `update`/`delete` 없는 id 메시지 + 비-0 종료 코드.
- `import`/`export` UTF-8 + 헤더, 스키마 일치.
- 데코레이터: 도메인 예외 → 사용자 메시지 변환 + 종료 코드.
- **CLI 출력 양식 일치**: §9 의 각 명령 예시 문자열을 stdout/stderr 캡처 결과와 비교(테이블 헤더·구분선·`[OK]`/`[ERROR]` 접두사·“데이터 없음” 메시지 포함).

---

## 12. 위험 요소 / 결정 보류 항목


| 항목                   | 위험                        | 완화책                                                                            |
| -------------------- | ------------------------- | ------------------------------------------------------------------------------ |
| `argparse` 단일 `-` 옵션 | 표준 관례와 충돌, 자동 도움말과 부합 어려움 | 모든 옵션을 `add_argument("-month", ...)` 처럼 명시 등록, 문서·테스트로 검증                      |
| JSONL 라인 손상          | 한 줄 오류가 전체 흐름 차단          | 손상 라인은 stderr 경고 후 스킵하고 카운트(추후 결정 필요 시 본 plan 갱신)                              |
| 원자적 교체               | Windows 호환성               | `os.replace` 사용(POSIX·Windows 모두 원자적), `tempfile.NamedTemporaryFile(dir=…)` 활용 |
| 카테고리 삭제 시 대체         | UX 정책 미정                  | 1차는 “사용 중이면 차단”만 구현, 보너스에서 ‘대체 카테고리 요구’ 검토                                     |


---

## 13. 완료 정의 (Definition of Done)

- subject §2.1 의 10개 명령이 정상 동작한다.
- `./data` 하위에 `transactions.jsonl`, `categories.jsonl`, `budgets.jsonl` 3개 파일이 분리 저장된다(subject §2.2).
- 모든 읽기 경로가 제너레이터다(파일 전체 로딩 없음).
- 데코레이터 1개 이상이 CLI 핸들러에 실제 적용되어 있다.
- 모든 공개 함수에 타입 힌트가 있고, 공개 함수에는 짧은 docstring 이 있다(.cursorrules §4).
- **§9 의 출력 양식과 stdout/stderr 출력이 일치한다**(테스트로 검증).
- `python -m unittest discover -s tests -p 'test_*.py' -v` 가 추가 패키지 없이 통과한다.
- `README.md` 가 실행법·저장 위치·CSV 스키마·명령 예시를 포함한다.
- 정상 종료 `0`, 오류 종료 비-0 으로 일관된다.

