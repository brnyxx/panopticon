# 판옵티콘 (Panopticon)

> **당신을 보지 않습니다. 당신의 MCP를 봅니다.**

`pano`는 AI 클라이언트에 설치된 MCP 서버를 찾아 미끼가 채워진 격리 환경에서 실제로 실행하고, 파일·호스트·tool 호출 단위로 *실제로 한 일*을 *선언한 것*과 비교해 보여줍니다.

```bash
uvx panopticon-mcp doctor        # 탐색 + config 검사, Docker 불필요
uvx panopticon-mcp watch --all   # Docker 또는 Podman 필요
```

원칙: 판단보다 관측이 먼저 · 관측하지 못한 것은 안전하다고 말하지 않음 · 사용자 홈은 컨테이너에 들어가지 않음(업로드·telemetry 없음).

구현 계획은 [`PLAN.md`](PLAN.md), 진행 상황은 [`PROGRESS.md`](PROGRESS.md). 에이전트는 [`../AGENTS.md`](../AGENTS.md)를 먼저 읽으세요.
