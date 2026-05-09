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
2026-05-01,expense,food,12000,점심,lunch,team
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

