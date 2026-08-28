# WATCH-005 — 예상 밖 설치 host

## 문제
설치 span이 package registry가 아닌 host에 연결했습니다.

## 영향
설치 과정이 알려진 package source 밖에서 네트워크 활동을 수행했습니다.

## 근거
정규화된 host와 allowlist 분류가 `__install__` span에 기록됩니다.

## 권장 조치
dependency를 고정하고 관련 없는 host에 연결하는 설치 hook을 제거하세요.

## 확인 방법
빈 cache에서 다시 빌드하고 설치 span의 모든 목적지를 확인하세요.

## 제한
알려진 registry도 제외 근거로 남습니다. 트래픽 capture가 불완전하면 `UNKNOWN`입니다.
