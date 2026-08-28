# WATCH-014 — startup 네트워크 활동

## 문제
protocol 준비 전의 예약된 startup span에서 네트워크 활동이 발생했습니다.

## 영향
tool 호출 또는 완료된 handshake가 event를 소유하기 전에 서버가 통신했습니다.

## 근거
네트워크 근거가 `__startup__` 반개방 span에 귀속됩니다.

## 권장 조치
startup beacon을 제거하거나 필요한 bootstrap 트래픽을 명시적으로 격리하세요.

## 확인 방법
서버를 다시 시작해 startup span에 네트워크 이벤트가 없는지 확인하세요.

## 제한
startup span 또는 네트워크 coverage가 불완전하면 `UNKNOWN`입니다.
