# 디버깅용 명령어 셋 (`commands.md`)

이 문서는 `budget_app`의 각 명령을 **정상 흐름**과 **예외 흐름**으로 빠르게 재현하기 위한 실행 커맨드 모음이다.

## 0) 실행 공통

프로젝트 루트에서 실행:

```bash
cd /Users/baejaemin/Project/codyssey/02-1.console_program
```

기본 실행 형식(모든 커맨드 공통):

```bash
python3 -m budget_app [command] [options...]
```

예시: `list` 실행

```bash
python3 -m budget_app list -data-dir ./data
```

## 1) 준비용 시드 커맨드

디버깅을 빠르게 시작하려면 먼저 데이터 하나를 만든다.

```bash
# 1) 기본 카테고리 확인 (food/transport/rent/etc 자동 부트스트랩)
python3 -m budget_app category list -data-dir ./data

# 2) add로 거래 1건 생성 (대화형)
python3 -m budget_app add -data-dir ./data
```

`add` 입력 예시:

```text
date (YYYY-MM-DD): 2026-05-08
type (income/expense): expense
category: food
amount: 12000
memo (optional): 점심
tags (comma separated, optional): lunch,team
```

## 2) 명령별 디버깅 커맨드 (정상/예외)

### 2.1 `add`

정상:

```bash
python3 -m budget_app add -data-dir ./data
```

예외(재입력 루프 확인):
- amount에 `-100` 입력 -> `[ERROR] amount 는 양수여야 합니다.` 출력 후 동일 프롬프트 재요청.

### 2.2 `list`

정상:

```bash
python3 -m budget_app list -limit 20 -data-dir ./data
```

예외:

```bash
python3 -m budget_app list -limit 0 -data-dir ./data
```

기대: `exit code 2`, `limit 는 양수여야 합니다.` (`UserInputError` 경로)

### 2.3 `search`

정상:

```bash
python3 -m budget_app search -category food -tag lunch -data-dir ./data
```

예외:

```bash
python3 -m budget_app search -type BAD -data-dir ./data
```

기대: `exit code 2`, `type 은 income/expense 중 하나여야 합니다.`

### 2.4 `summary`

정상:

```bash
python3 -m budget_app summary -month 2026-05 -top 5 -data-dir ./data
```

예외:

```bash
python3 -m budget_app summary -month 2026-13 -data-dir ./data
```

기대: `exit code 2`, `year_month 형식은 YYYY-MM 이어야 합니다.`

### 2.5 `budget set`

정상:

```bash
python3 -m budget_app budget set -month 2026-05 -amount 1000000 -data-dir ./data
```

예외:

```bash
python3 -m budget_app budget set -month 2026-05 -amount -1 -data-dir ./data
```

기대: `exit code 2`, `amount 는 양수여야 합니다.`

### 2.6 `category`

정상:

```bash
python3 -m budget_app category add salary -data-dir ./data
python3 -m budget_app category list -data-dir ./data
python3 -m budget_app category remove salary -data-dir ./data
```

예외:

```bash
# 중복 추가: [WARN] 경로(종료코드 0)
python3 -m budget_app category add food -data-dir ./data

# 사용 중 카테고리 삭제: [ERROR] 경로(종료코드 1)
python3 -m budget_app category remove food -data-dir ./data
```

### 2.7 `update`

정상(먼저 list로 id 확인):

```bash
python3 -m budget_app list -data-dir ./data
python3 -m budget_app update -id <거래ID> -amount 13000 -memo "점심(2)" -data-dir ./data
```

예외:

```bash
# 없는 id
python3 -m budget_app update -id ghost -amount 1 -data-dir ./data

# 잘못된 type
python3 -m budget_app update -id <거래ID> -type BAD -data-dir ./data
```

### 2.8 `delete`

정상:

```bash
python3 -m budget_app delete -id <거래ID> -data-dir ./data
```

예외:

```bash
python3 -m budget_app delete -id ghost -data-dir ./data
```

기대: `exit code 1`, `해당 id 의 거래를 찾을 수 없습니다.`

### 2.9 `import`

샘플 CSV 생성:

```bash
cat > /tmp/in_ok.csv <<'EOF'
date,type,category,amount,memo,tags
2026-05-01,expense,food,12000,점심,"lunch,team"
EOF
```

정상:

```bash
python3 -m budget_app import -from /tmp/in_ok.csv -data-dir ./data
```

부분 성공/예외 재현용 CSV:

```bash
cat > /tmp/in_partial.csv <<'EOF'
date,type,category,amount,memo,tags
2026-05-01,expense,food,12000,ok,a
2026-05-02,expense,food,-100,bad,b
EOF
python3 -m budget_app import -from /tmp/in_partial.csv -data-dir ./data
```

전체 실패:

```bash
cat > /tmp/in_fail.csv <<'EOF'
date,type,category,amount,memo,tags
bad,expense,food,100,fail,
EOF
python3 -m budget_app import -from /tmp/in_fail.csv -data-dir ./data
```

### 2.10 `export`

정상(`-month`):

```bash
python3 -m budget_app export -out /tmp/out_2026_05.csv -month 2026-05 -data-dir ./data
```

정상(`-from` + `-to`):

```bash
python3 -m budget_app export -out /tmp/out_range.csv -from 2026-05-01 -to 2026-05-31 -data-dir ./data
```

예외(조건 누락):

```bash
python3 -m budget_app export -out /tmp/out_fail.csv -data-dir ./data
```

기대: `exit code 2`, `export 는 -month 또는 -from + -to 중 하나가 필수입니다.`

## 3) 도움말 / 종료 코드 체크

도움말:

```bash
python3 -m budget_app -help
python3 -m budget_app list -help
```

종료 코드 확인:

```bash
python3 -m budget_app export -out /tmp/out_fail.csv -data-dir ./data
echo $?
```

기대 정책:
- 정상: `0`
- 입력 검증 실패: `2`
- 그 외 운영 오류: `1`

## 4) 과제 요구사항 기준 추가 검증 셋

아래는 `subject.md`의 필수 요구사항(초기 실행, 데이터 없음, 조합 검색, 스키마 엄격성, 영속성)을 빠짐없이 확인하기 위한 보강 커맨드다.

### 4.1 초기 실행/부트스트랩 검증 (`§4.5`, `§2.2`)

```bash
rm -rf /tmp/budget_empty && mkdir -p /tmp/budget_empty

python3 -m budget_app category list -data-dir /tmp/budget_empty
ls -1 /tmp/budget_empty
```

확인 포인트:
- 저장 파일 3개가 자동 생성되는지 확인 (`transactions`, `categories`, `budgets`)
- 카테고리 초기 정책(A/B)이 문서화한 동작과 일치하는지 확인

### 4.2 영속성 검증 (재실행 후 유지) (`§4.4`)

```bash
rm -rf /tmp/budget_persist && mkdir -p /tmp/budget_persist

python3 -m budget_app budget set -month 2026-05 -amount 1000000 -data-dir /tmp/budget_persist
python3 -m budget_app summary -month 2026-05 -data-dir /tmp/budget_persist
python3 -m budget_app summary -month 2026-05 -data-dir /tmp/budget_persist
```

확인 포인트:
- 프로세스를 다시 실행해도 예산/요약 결과가 유지되는지 확인

### 4.3 데이터 없음 메시지 검증 (`§4.10`, `§2.1`)

```bash
rm -rf /tmp/budget_nodata && mkdir -p /tmp/budget_nodata

python3 -m budget_app summary -month 2030-01 -data-dir /tmp/budget_nodata
python3 -m budget_app search -category food -data-dir /tmp/budget_nodata
python3 -m budget_app list -data-dir /tmp/budget_nodata
```

확인 포인트:
- summary에서 `"데이터 없음"`이 명확히 출력되는지 확인
- search/list도 빈 결과 메시지가 모호하지 않은지 확인

### 4.4 검색 필터 조합 검증 (`§4.9`)

```bash
python3 -m budget_app search -from 2026-05-01 -to 2026-05-31 -type expense -category food -q 점심 -tag lunch -data-dir ./data
```

확인 포인트:
- 필터 조합이 AND 조건으로 동작하는지 확인
- 결과 정렬이 최신순인지 확인

### 4.5 경계값/입력 검증 보강 (`§4.3`)

```bash
python3 -m budget_app list -limit 1 -data-dir ./data
python3 -m budget_app list -limit 999999 -data-dir ./data

python3 -m budget_app summary -month 2026-00 -data-dir ./data
python3 -m budget_app summary -month 2026-13 -data-dir ./data

python3 -m budget_app budget set -month 2026-05 -amount 0 -data-dir ./data
python3 -m budget_app budget set -month 2026-05 -amount -10 -data-dir ./data
```

확인 포인트:
- 입력 검증 실패 케이스들이 모두 종료코드 `2`로 통일되는지 확인

### 4.6 update 부분 수정/무변경 검증 (`§4.8`)

```bash
python3 -m budget_app list -data-dir ./data
python3 -m budget_app update -id <거래ID> -memo "메모만 수정" -data-dir ./data
python3 -m budget_app update -id <거래ID> -tags "a,b,c" -data-dir ./data
python3 -m budget_app update -id <거래ID> -data-dir ./data
```

확인 포인트:
- 일부 필드만 수정할 때 다른 필드가 보존되는지 확인
- 변경 필드 없이 `update` 호출 시 정책(오류/무시)이 일관되는지 확인

### 4.7 category 삭제 정책 검증 (`§4.12`)

```bash
python3 -m budget_app category add travel -data-dir ./data
python3 -m budget_app category remove travel -data-dir ./data
python3 -m budget_app category remove food -data-dir ./data
```

확인 포인트:
- 미사용 카테고리는 삭제되는지 확인
- 사용 중 카테고리는 차단(또는 대체 요구) 정책대로 동작하는지 확인

### 4.8 import/export 스키마 엄격성 + round-trip (`§4.13`)

잘못된 헤더:

```bash
cat > /tmp/in_bad_header.csv <<'EOF'
d,t,c,a,m,tags
2026-05-01,expense,food,1000,test,a
EOF
python3 -m budget_app import -from /tmp/in_bad_header.csv -data-dir ./data
```

export 후 재import:

```bash
rm -rf /tmp/budget_roundtrip && mkdir -p /tmp/budget_roundtrip
python3 -m budget_app export -out /tmp/out_round.csv -month 2026-05 -data-dir ./data
python3 -m budget_app import -from /tmp/out_round.csv -data-dir /tmp/budget_roundtrip
python3 -m budget_app list -data-dir /tmp/budget_roundtrip
```

확인 포인트:
- UTF-8 + 헤더 + 필수 컬럼 검증이 제대로 되는지 확인
- round-trip 후 데이터가 깨지지 않는지 확인

### 4.9 도움말/옵션 표기 일관성 (`§4.1`)

```bash
python3 -m budget_app -help
python3 -m budget_app add -help
python3 -m budget_app search -help
python3 -m budget_app export -help
```

확인 포인트:
- 문서에 고정한 옵션 표기(`-month`, `-from`, `-to`)와 실제 help 출력이 일치하는지 확인

### 4.10 종료코드 매트릭스 (`§4.15`)

```bash
# 정상(0)
python3 -m budget_app list -data-dir ./data; echo $?

# 입력 검증 실패(2)
python3 -m budget_app export -out /tmp/o.csv -data-dir ./data; echo $?

# 운영 오류(1) - 예: 존재하지 않는 파일 import
python3 -m budget_app import -from /tmp/not_exists.csv -data-dir ./data; echo $?
```

확인 포인트:
- 종료코드 정책(0/2/1)이 실제 구현과 동일한지 확인

