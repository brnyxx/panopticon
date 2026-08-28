# WATCH-007 — proxy 우회 시도

## 문제
sandbox proxy 정책이 활성화된 동안 direct egress가 drop되었습니다.

## 영향
서버가 관찰 가능한 proxy 경로를 우회하는 route를 시도했습니다.

## 근거
proxy 또는 firewall 근거에 결정적인 `DROP` 이벤트와 목적지가 기록됩니다.

## 권장 조치
트래픽을 설정된 proxy로 보내거나 direct 연결을 제거하세요.

## 확인 방법
호출을 반복해 direct-drop 이벤트가 발생하지 않는지 확인하세요.

## 제한
proxy log가 없으면 우회가 없었다고 보지 않고 `UNKNOWN`으로 표시합니다.
