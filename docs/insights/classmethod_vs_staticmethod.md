# `from_dict`에서 `@classmethod`를 쓰는 이유

## 배경

현재 Phase 1 모델은 `to_dict()` / `from_dict()`를 클래스 내부에 두는 형태로 구현되어 있다.

- 참조: [`models.py`](../../src/budget_app/models.py)
- 관련 요구: [`plan.md`](../plan.md) §4
  - 직렬화/역직렬화 헬퍼는 dataclass 모듈 내부에 두고, 외부에는 `to_dict()` / `from_dict()`만 노출

`from_dict()`는 크게 세 가지 방식으로 구현할 수 있다.

1. `@classmethod` + `cls(...)`
2. `@staticmethod` + `Transaction(...)` 같은 클래스명 직접 호출
3. 모듈 레벨 함수 `transaction_from_dict(payload)`

이 문서는 세 방식의 장단점과, 이 프로젝트에서 어떤 기준으로 선택할지 정리한다.

---

## 1) `@classmethod` 방식

예시(현재 코드의 핵심 구조):

```python
@classmethod
def from_dict(cls, payload: dict[str, Any]) -> "Transaction":
    ...
    return cls(...)
```

### 장점

- 대체 생성자 의도가 명확하다.
  - 인스턴스 메서드가 아니라, "새 객체를 만드는 클래스 API"라는 의미가 바로 드러난다.
- 상속에 유연하다.
  - `ChildTransaction.from_dict(...)` 호출 시 `cls`가 자식 클래스를 가리키므로 `cls(...)`가 자식 생성자를 호출한다.
- API 응집도가 좋다.
  - `to_dict()`/`from_dict()`가 같은 클래스 안에 있어 사용자가 찾기 쉽다.
- 테스트/호출이 직관적이다.
  - `Transaction.from_dict(payload)`처럼 읽힌다.

### 단점

- 현재 과제 범위(Phase 1)에서는 상속을 쓰지 않으므로 체감 이점이 작다.
- `@staticmethod`보다 문법이 한 단계 더 있다(`cls` 이해 필요).
- 팀원 입장에서 "왜 굳이 classmethod?"라는 인지 비용이 생길 수 있다.

---

## 2) `@staticmethod` 방식

예시:

```python
@staticmethod
def from_dict(payload: dict[str, Any]) -> "Transaction":
    ...
    return Transaction(...)
```

### 장점

- 단순하다.
  - `cls` 개념 없이 바로 읽힌다.
- 현재 클래스가 고정되어 있음을 명확히 보여준다.

### 단점

- 상속 대응력이 떨어진다.
  - 자식 클래스에서 `from_dict`를 그대로 쓰면 부모(`Transaction`) 인스턴스를 만들 가능성이 크다.
- 클래스명 하드코딩이 들어간다.
  - 리팩토링 시 변경 지점이 늘어날 수 있다.

---

## 3) 모듈 함수 방식

예시:

```python
def transaction_from_dict(payload: dict[str, Any]) -> Transaction:
    return Transaction(...)
```

### 장점

- 함수형 스타일로 단순하다.
- "직렬화 로직은 순수 함수"라는 구조를 선호할 때 명확하다.

### 단점

- API가 분산된다.
  - `Transaction.to_dict()`는 클래스 안에 있고, `from_dict`는 모듈 밖에 있어 짝이 약해진다.
- 요구사항(클래스 중심 노출) 관점에서 일관성이 떨어질 수 있다.

---

## `@classmethod`가 "꼭" 필요한가?

필수는 아니다.

- 지금 과제 스코프만 보면 `@staticmethod`로도 충분히 동작한다.
- 다만 `from_dict`를 "대체 생성자"로 볼 때는 `@classmethod`가 Python 관례에 가장 가깝다.

즉, 선택 기준은 성능이 아니라 **의도 표현 + 확장 가능성 + 팀 컨벤션**이다.

---

## 이 프로젝트(현재 상태)에서의 권장 정리

현재 코드와 학습 맥락을 기준으로 보면 다음이 현실적이다.

- `to_dict`/`from_dict`는 클래스 내부에 유지한다. (요구사항과 가독성 측면)
- `from_dict`는 `@classmethod`를 유지한다.
  - 이유: 대체 생성자 의도 명확, 향후 확장 시 오버라이드 부담 감소
- 다만 상속을 전혀 고려하지 않는 학습 단계에서는 `@staticmethod`도 허용 가능하다.
  - 이 경우 "현재는 단순성을 우선"이라는 팀 규칙을 문서로 남기는 것이 좋다.

---

## 상속 시 동작 요약

`@classmethod` + `cls(...)`일 때:

- `Parent.from_dict(...)` -> `Parent(...)`
- `Child.from_dict(...)` -> `Child(...)`

오버라이드는 "자식 생성자 시그니처가 달라졌을 때"만 필요하다.

예: 자식이 필드를 추가해 `Child(month, amount, source)`를 요구하면,
부모 `from_dict`는 `source`를 모르므로 자식에서 오버라이드해야 한다.

---

## 결론

- "굳이?"라는 감각은 타당하다.
- 그래도 `from_dict`가 클래스 생성 책임을 갖는 이상, `@classmethod`는 가장 표준적이고 설명 가능한 선택이다.
- 지금 코드베이스에서는 **단순성(현재)**과 **유연성(미래)**의 균형을 위해 `@classmethod` 유지가 무난하다.
