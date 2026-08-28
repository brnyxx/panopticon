# WATCH-006 — 선언 밖 개인 config 읽기

## 문제
tool이 선언 범위 밖의 개인 shell, Git 또는 application config 파일을 읽었습니다.

## 영향
서버가 귀속된 tool 범위와 관련 없는 사용자별 설정에 접근했습니다.

## 근거
읽기 근거에 정규화된 config 경로, tool, span이 기록됩니다.

## 권장 조치
읽기를 제거하거나 명시적인 합성 config로 범위를 좁히세요.

## 확인 방법
호출을 반복해 개인 config 경로를 읽지 않는지 확인하세요.

## 제한
stat 근거는 읽기와 구분됩니다. 추적이 불완전하면 `UNKNOWN`입니다.
