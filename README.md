# 콘솔 가계부 (`budget_app`)

Python 콘솔용 가계부 앱입니다. 데이터는 JSONL 파일에 저장하고, CSV로 가져오기·보내기를 지원합니다.

## 실행 환경

- **Python**: 3.14 권장 (`docs/plan.md` 기준)
- **작업 디렉터리**: 이 저장소의 `02-1.console_program` 루트에서 실행하는 것을 가정합니다.

```bash
cd /path/to/02-1.console_program
```

`budget_app` 을 찾지 못하면 `PYTHONPATH` 에 프로젝트 루트를 넣습니다.

```bash
PYTHONPATH=. python3 -m budget_app -help
```

## 실행 형식

```text
python3 -m budget_app <command> [options...]
```

기본 데이터 디렉터리는 **`./data`** 입니다. 다른 경로를 쓰려면 **`-data-dir <path>`** 를 붙입니다.

## 데이터 위치 (`./data`)

| 파일 | 설명 |
|------|------|
| `data/transactions.jsonl` | 거래 한 줄당 JSON 하나 |
| `data/categories.jsonl` | 카테고리 한 줄당 JSON 하나 |
| `data/budgets.jsonl` | 월별 예산 한 줄당 JSON 하나 |

첫 실행 시 파일이 없으면 생성되며, 카테고리는 기본값(`food`, `transport`, `rent`, `etc`)이 자동으로 채워집니다.

### JSONL 스키마 (한 줄 = 한 레코드)

- **거래** (`transactions.jsonl`): `id`, `type` (`income` \| `expense`), `date` (`YYYY-MM-DD`), `amount` (정수), `category`, `memo`, `tags` (문자열 배열)
- **카테고리** (`categories.jsonl`): `name` (문자열)
- **예산** (`budgets.jsonl`): `year_month` (`YYYY-MM`), `amount` (정수) — 과거에 `month` 키로 저장된 줄도 읽을 때 호환됩니다.

### CSV 스키마 (import / export)

- **인코딩**: UTF-8
- **헤더 한 줄** (열 순서 고정):

  `date,type,category,amount,memo,tags`

- **열 의미**
  - `date`: `YYYY-MM-DD`
  - `type`: `income` 또는 `expense`
  - `category`: 등록된 카테고리 이름
  - `amount`: 양의 정수
  - `memo`: 자유 텍스트 (비어 있어도 됨)
  - `tags`: 쉼표로 구분된 태그 (예: `lunch,team`)

가져오기는 `import -from <파일>`, 보내기는 `export -out <파일>` 이며, 보내기는 **`-month YYYY-MM`** 또는 **`-from` / `-to`** 날짜 범위 중 하나가 필요합니다.

## 주요 명령 예시 (과제 요약 · `docs/subject.md` §2.1)

아래는 `-data-dir ./data` 를 생략한 예입니다. 필요하면 모든 명령에 동일하게 붙이면 됩니다.

```bash
# 거래 추가 (대화형)
python3 -m budget_app add

# 목록 / 검색 / 월별 요약
python3 -m budget_app list -limit 20
python3 -m budget_app search -category food -type expense
python3 -m budget_app summary -month 2026-05 -top 5

# 예산
python3 -m budget_app budget set -month 2026-05 -amount 500000

# 카테고리
python3 -m budget_app category list
python3 -m budget_app category add hobby
python3 -m budget_app category remove hobby

# 수정 / 삭제 (거래 id 필요)
python3 -m budget_app update -id <id> -amount 15000
python3 -m budget_app delete -id <id>

# CSV
python3 -m budget_app import -from ./path/to/in.csv
python3 -m budget_app export -out ./path/to/out.csv -month 2026-05
```

옵션은 과제 규칙에 따라 **단일 하이픈** 형태입니다 (`-help`, `-limit`, `-from`, `-to`, `-month` 등).

## 사전 고정 결정 (`docs/plan.md` §2 와 동일)

| 항목 | 결정 | 근거 |
|------|------|------|
| 저장 포맷 | **JSONL** | 라인 단위 스트리밍에 적합, 표준 `json` 만으로 처리 |
| 카테고리 초기 동작 | **기본 카테고리 자동 생성** (`food`, `transport`, `rent`, `etc`) | 첫 실행 UX |
| `update` 입력 | **옵션 기반** (`update -id <id>` 및 변경 필드 옵션) | 스크립트·CLI 일관성 |
| 데이터 디렉터리 | 기본 **`./data`**, `-data-dir <path>` 로 변경 | 과제 권장 |
| 옵션 표기 | 단일 `-` (`-help`, `-limit`, …) | 과제 §4.1 |
| 테스트 러너 | 표준 **`unittest`** (`python -m unittest discover -s tests -p 'test_*.py' -v`) | 프로젝트 규칙 |

## 테스트

```bash
cd /path/to/02-1.console_program
PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_*.py' -v
```

(`pytest` 를 쓸 경우 `pytest.ini` 의 `pythonpath` 가 로컬 레이아웃과 맞는지 확인하세요.)

## 문서

- 요구사항: `docs/subject.md`
- 구현 계획·모델·저장 정책: `docs/plan.md`
- 디버깅용 커맨드 모음: `docs/commands.md`
