# WATCH-009 — 광범위한 파일 열거

## 문제
한 호출이 개인 콘텐츠 directory 아래의 서로 다른 경로를 열 개 이상 stat 또는 read했습니다.

## 영향
관찰된 pattern이 좁은 요청 경로 대신 광범위한 collection을 열거했습니다.

## 근거
귀속된 span 안에서 정규화된 서로 다른 경로와 operation을 계산합니다.

## 권장 조치
탐색을 명시된 입력 경로로 제한하고 기본 recursive discovery를 제거하세요.

## 확인 방법
호출을 반복해 서로 다른 경로 수가 문서화된 threshold보다 작은지 확인하세요.

## 제한
threshold는 열 개입니다. 파일 coverage가 불완전하면 threshold 미만 결과도 `UNKNOWN`입니다.
