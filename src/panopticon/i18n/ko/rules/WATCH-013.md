# WATCH-013 — read-only hint 모순

## 문제
read-only로 표시된 tool이 파일 write 또는 클라이언트에서 보이는 network POST를 수행했습니다.

## 영향
관찰된 behavior가 client와 reviewer가 사용하는 tool annotation과 모순됩니다.

## 근거
write 또는 POST 근거가 annotation이 있는 tool-call span에 귀속됩니다.

## 권장 조치
mutation을 제거하거나 annotation과 선언을 수정하세요.

## 확인 방법
호출을 반복해 read-only hint 아래에서 write 또는 보이는 POST가 없는지 확인하세요.

## 제한
불투명한 TLS 활동으로 POST body를 확정하지 않으며 `UNKNOWN`으로 표시합니다.
