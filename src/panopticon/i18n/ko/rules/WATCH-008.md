# WATCH-008 — 선언 밖 외부 process

## 문제
tool이 권위 있는 선언 밖의 외부 process를 실행했습니다.

## 영향
관찰된 process가 귀속된 tool 범위보다 실행 범위를 넓힙니다.

## 근거
process 근거에 executable basename, 인자 분류, span이 기록됩니다.

## 권장 조치
subprocess를 제거하거나 정확한 executable과 목적을 선언하세요.

## 확인 방법
호출을 반복하고 tooling 제외 대상이 아닌 모든 executable을 선언과 비교하세요.

## 제한
정확히 일치하는 interpreter와 package tool 제외도 근거로 남습니다. coverage가 불완전하면 `UNKNOWN`입니다.
