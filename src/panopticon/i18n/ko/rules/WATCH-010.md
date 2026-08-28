# WATCH-010 — 선언 범위와 관찰 범위 일치

## 문제
이 정보 조건은 권위 있는 선언이 관찰된 모든 항목을 포함할 때만 사용할 수 있습니다.

## 영향
보안 verdict를 부여하지 않고 완전한 비교 경계를 기록합니다.

## 근거
적용 가능한 source coverage가 모두 complete이고 모든 경로, host, process가 tool별 범위와 일치합니다.

## 권장 조치
선언을 최신으로 유지하고 완전한 관찰 coverage를 보존하세요.

## 확인 방법
관찰을 반복해 적용 가능한 모든 stage가 계속 complete인지 확인하세요.

## 제한
suppression, 제외, 미포함 event 또는 불완전 stage가 있으면 이 조건은 `UNKNOWN`이거나 일치하지 않습니다.
