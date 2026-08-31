# 판옵티콘 (Panopticon)

> **당신을 보지 않습니다. 당신의 MCP를 봅니다.**

[English guide](https://github.com/brnyxx/panopticon/blob/main/README.md)

`pano`는 AI 클라이언트에 설정된 MCP 서버를 찾아, 미끼 데이터가 든 격리 환경에서 선택한
서버를 실행합니다. 파일·네트워크 호스트·프로세스와 선언 내용 대비 관측 내용을 기록합니다.
이 결과는 관측 근거이며 사용자를 대신해 판정을 내리지 않습니다.

## 처음 한 번 따라 하기

현재 공개된 PyPI 릴리스를 설치하고, 설정된 서버 이름을 확인한 뒤 하나를 골라 관측합니다.

```bash
uv tool install panopticon-mcp==1.0.1
pano doctor --offline
pano watch SERVER_NAME --offline
```

현재 checkout된 repository는 공개되지 않은 1.0.2 개발 버전입니다.
`uv sync --all-extras`는 contributor setup이며 공개 설치 경로가 아닙니다.

`SERVER_NAME`은 `doctor`가 출력한 실제 이름으로 바꿉니다. 셸 꺾쇠 placeholder가 아닙니다.
패키지 설치는 `pano` 실행 전에 선택한 레지스트리에 연결합니다. 그 뒤 `--offline`은
Panopticon의 registry, advisory, package lookup, semantic analyzer 외부 경로를 끕니다.
선택한 MCP가 시도한 트래픽은 Panopticon의 제품 조회가 아니라 sandbox 관측 근거로 남습니다.
`doctor`에는 Docker나 Podman이 필요하지 않으며, 로컬 `watch`에는 필요합니다.
깨끗한 runtime에서는 첫 offline observation 전에
[Offline watch용 image 준비](getting-started.ko.md#offline-watch용-image-준비)를 따릅니다.

한 번만 버전을 확인하려면 `uvx --from 'panopticon-mcp==1.0.1' pano version`을 실행합니다. 출력은
`pano 1.0.1 (schema 1.0)`입니다. 다른 설치 방법, 업그레이드, 되돌리기, 폐쇄망 사용법은
[설치 및 릴리스 안내](release.md)를 보세요.

두 언어 데모 소스는
[`site/template.html`](../site/template.html)에서 시작합니다. `scripts/build_site.py`가
locale key 동일성을 검사하고 두 경로를 결정적으로 빌드하며, SHA가 고정된 Pages workflow가
`main`의 생성 산출물을 배포합니다. 페이지에는 analytics, cookie, local storage, runtime
remote resource가 없습니다. GitHub Pages가 처리하는 요청에는 GitHub의 호스팅 정책이
적용됩니다.

## 목적에 맞는 흐름 선택

| 하고 싶은 일 | 시작 명령 | 요구사항 또는 경계 |
|---|---|---|
| 설정된 MCP 찾기 | `pano doctor --offline` | Container runtime 불필요 |
| 로컬 MCP 하나 관찰 | `pano watch SERVER_NAME --offline` | Docker 또는 Podman. `doctor`가 출력한 정확한 이름 사용 |
| Finding 하나 설명 | `pano explain RULE_ID --lang ko` | Stable rule ID 사용 |
| 반복 관찰 비교 | `pano baseline create` 후 `pano diff SERVER_NAME` | 하나의 installation에 대한 canonical evidence 유지 |
| MCP 저장소 분석 | `pano scan . --mode quick --offline` | Standard/deep 외부 경로는 privacy 문서에 명시 |
| 저장소 policy 적용 | `pano ci . --mode standard --fail-on high` | SARIF를 쓰고 문서화된 exit-code 우선순위 사용 |
| Client configuration 변경 | `pano fix SERVER_NAME --dry-run --offline` | Diff 검토 후 별도 `--yes` 호출 |
| MCP command wrap 또는 복원 | `pano install CLIENT --dry-run` / `pano uninstall CLIENT --dry-run` | Undo를 위해 원래 command 보존 |

설치 matrix, 전체 첫 사용 흐름, 상태표, exit code, artifact 위치, 정리, 문제 해결, command
예시는 **[Panopticon 시작하기](getting-started.ko.md)**에 있습니다.

## AI agent에서 사용

Agent는 JSON을 읽고 불확실성을 유지해야 합니다. 모든 nonzero exit를 process crash로,
완료된 stage를 제품 판정으로 바꾸지 않습니다. 기본 순서는 다음과 같습니다.

```bash
pano version
pano doctor --offline --json
pano watch SERVER_NAME --offline --json
```

Agent는 별도 명시적 승인 없이 `--all`, 실제 환경 변수, destructive call, deep semantic
analysis, `--yes`, local evidence 삭제를 사용하지 않습니다. 복사 가능한 agent prompt,
response schema, exit-code policy, confirmation boundary는
**[Agent 실행 가이드](agent-guide.md)**에 있습니다.

## 결과 읽기

- `COMPLETE`: 해당 단계가 표시된 적용 범위로 완료되었습니다.
- `UNKNOWN`: 현재 근거만으로는 결론을 낼 수 없습니다.
- `INCOMPLETE`: 요청한 관측이 필요한 작업을 모두 마치지 못했습니다.
- `UNSUPPORTED`: 이 플랫폼·모드·대상에서는 해당 차원을 관측할 수 없습니다.

이 상태들은 서로 바꿔 쓸 수 없습니다. 예를 들어 원격 관측은 서버 쪽 파일·프로세스 활동을
볼 수 없어 그 차원을 `UNSUPPORTED`로 표시합니다. `WATCH-003`, `CFG-008`, `HIST-002` 같은
규칙 ID는 정확한 검사를 가리킵니다. 설명은 다음과 같이 확인합니다.

```bash
pano explain WATCH-003
```

터미널 결과와 근거 카드를 함께 검토하세요. 카드는 관측하지 못한 부분을 다른 상태로 바꾸지
않고 적용 범위와 규칙 ID를 그대로 표시합니다.

## 설계 방식

- `cli`는 parse와 render를 담당하고 `engine`이 typed outcome과 exit policy를 소유합니다.
- Collector는 exhaustive status, stable `reason_code`, coverage, evidence, diagnostic을
  반환합니다.
- Sandbox에는 사용자 home이 아니라 생성한 decoy home이 들어갑니다. `--self`만 project
  source를 read-only로 명시적으로 mount합니다.
- `store`만 artifact를 쓰며 persistence 전에 canonicalize, leak check, atomic replace를
  수행합니다.
- Demo는 bilingual locale catalog, Python standard-library builder, local browser asset으로
  결정적으로 생성됩니다.

[Architecture](../ARCHITECTURE.md), [demo design system](../DESIGN.md),
[frozen decisions](DECISIONS.md), [product build plan](../panopticon-buildplan.md)에서 전체
계약을 확인할 수 있습니다.

## 개인정보와 정리

관측 전에는 특히 실제 환경 변수 전달이나 심층 분석을 사용하기 전에
[개인정보 및 외부 통신 표](privacy.md)을 읽으세요. 저장 전 모든 산출물은 누출 검사를
통과해야 합니다. 표준/심층 스캔은 advisory 확인을 위해 잠금 파일에서 확인한 정확한 패키지
이름과 버전만 OSV로 보내며 소스는 보내지 않습니다. `--offline`은 이 경로도 끕니다. 저장
위치·기록 보존·설정 되돌리기·패키지 되돌리기는 [릴리스 안내](release.md)와
[제한 사항](limitations.md)에 있습니다.
