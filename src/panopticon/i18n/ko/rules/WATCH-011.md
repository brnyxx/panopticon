# WATCH-011 — 비교 판단 보류

## 문제
관찰된 tool의 선언이 없거나, 부분적이거나, 권위가 없습니다.

## 영향
관찰된 behavior를 주장된 범위와 빠짐없이 비교할 수 없습니다.

## 근거
선언 authority와 coverage 필드가 빠진 비교 경계를 나타냅니다.

## 권장 조치
tool별 권위 있는 completeness assertion과 명시적인 범위를 제공하세요.

## 확인 방법
선언을 다시 불러와 authority와 coverage가 complete인지 확인하세요.

## 제한
이 규칙은 판단 보류를 표시합니다. 누락된 정보를 pass로 바꾸지 않습니다.
