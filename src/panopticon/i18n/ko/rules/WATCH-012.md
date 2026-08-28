# WATCH-012 — 다수의 외부 URL

## 문제
remote response에 서로 다른 외부 URL이 열 개 이상 포함되었습니다.

## 영향
response가 후속 접근이 가능한 광범위한 목적지를 노출했습니다.

## 근거
클라이언트에서 보이는 response 근거에 정규화된 URL host와 개수가 기록됩니다.

## 권장 조치
요청 결과에 필요한 URL만 반환하세요.

## 확인 방법
요청을 반복해 서로 다른 외부 URL 수가 열 개 미만인지 확인하세요.

## 제한
불투명하거나 잘린 response에서는 threshold 미만 결과를 `UNKNOWN`으로 유지합니다.
