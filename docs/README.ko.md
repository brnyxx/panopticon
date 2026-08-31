<div align="center">

<img src="https://raw.githubusercontent.com/brnyxx/panopticon/main/.github/assets/logo.svg" alt="선택한 주황색 구간 하나, 관찰 링 하나, 터미널 커서 동공으로 구성한 Panopticon aperture mark" width="96"/>

<img src="https://raw.githubusercontent.com/brnyxx/panopticon/main/.github/assets/hero.svg" alt="MCP 하나를 선택해 생성된 미끼 환경에서 실행하고 근거 기록을 확인하는 Panopticon 흐름" width="920"/>

</div>

# 판옵티콘 (Panopticon)

> **당신을 보지 않습니다. 당신의 MCP를 봅니다.**

[English guide](https://github.com/brnyxx/panopticon/blob/main/README.md)

`pano`는 AI 클라이언트에 설정된 MCP 서버를 찾아, 미끼 데이터가 든 격리 환경에서 선택한
서버를 실행합니다. 파일·네트워크 호스트·프로세스와 선언 내용 대비 관측 내용을 기록합니다.
이 결과는 관측 근거이며 사용자를 대신해 판정을 내리지 않습니다.

**[한국어·영어 인터랙티브 제품 안내 보기](https://brnyxx.github.io/panopticon/ko/)** —
analytics, cookie, browser storage, 자동 remote runtime request가 없는 정적 데모입니다.

## 처음 한 번 따라 하기

현재 공개된 PyPI 릴리스를 설치하고, 설정된 서버 이름을 확인한 뒤 하나를 골라 관측합니다.

```bash
uv tool install panopticon-mcp==1.0.1
pano doctor --offline
pano watch SERVER_NAME --offline
```

실행 흐름:

1. `doctor`는 third-party code를 시작하지 않고 설정된 이름을 보여 줍니다. Docker나
   Podman도 필요하지 않습니다.
2. `SERVER_NAME`을 출력된 정확한 이름 하나로 바꿉니다. `NAME_AMBIGUOUS` 상태에서는
   Panopticon이 대상을 추측하지 않습니다.
3. 별도 실행 승인 뒤 `watch`는 생성된 미끼 홈에서 해당 MCP를 실행하고 파일·네트워크·
   프로세스·누출·스냅샷 근거를 기록합니다.
4. 결과에는 상태, `reason_code`, 모든 관찰 차원, finding ID, artifact 경로가 남습니다.
   부족한 근거도 그대로 표시합니다.

첫 관찰 전 확인 사항:

- 패키지 설치는 `pano` 실행 전에 선택한 registry에 연결합니다. 이후 `--offline`은
  Panopticon registry, advisory, package lookup, semantic analyzer 외부 경로를 끕니다.
- 선택한 MCP가 시도한 트래픽은 Panopticon 조회가 아니라 sandbox 관찰 근거로 남습니다.
- 로컬 `watch`에는 Docker 또는 Podman이 필요합니다. 깨끗한 runtime에서는
  [digest-pinned image를 먼저 준비](getting-started.ko.md#offline-watch용-image-준비)합니다.
- 현재 checkout은 공개되지 않은 1.0.2 개발 버전입니다. `uv sync --all-extras`는
  contributor setup이며 공개 설치 경로가 아닙니다.

한 번만 버전을 확인하려면 `uvx --from 'panopticon-mcp==1.0.1' pano version`을 실행합니다. 출력은
`pano 1.0.1 (schema 1.0)`입니다. 다른 설치 방법, 업그레이드, 되돌리기, 폐쇄망 사용법은
[설치 및 릴리스 안내](release.md)를 보세요.

## 기록 읽기

- `COMPLETE`: 이름 붙은 관찰 차원이 표시된 범위로 완료되었습니다.
- `UNKNOWN`: 현재 근거만으로는 결론을 낼 수 없습니다.
- `INCOMPLETE`: 요청한 관찰이 필요한 작업을 모두 마치지 못했습니다.
- `UNSUPPORTED`: 이 플랫폼·모드·대상에서는 해당 차원을 관찰할 수 없습니다.

이 상태들은 서로 바꿔 쓸 수 없습니다. 예를 들어 `WATCH-001`은 미끼 표식이 외부 전송
지점에 도달했음을 나타내며 표식 값 자체는 표시하지 않습니다. 자세한 설명은
`pano explain WATCH-001 --lang ko`로 확인합니다.

<div align="center">
<img src="https://raw.githubusercontent.com/brnyxx/panopticon/main/.github/assets/evidence-card.png" alt="전체 관찰 범위 INCOMPLETE, 파일과 네트워크 COMPLETE, 프로세스 UNSUPPORTED, WATCH-001 finding 하나와 leak finding 하나를 표시한 설명용 Panopticon reporter 결과" width="720"/>
</div>

<p align="center"><sub>정해진 fixture를 Panopticon의 deterministic PNG reporter로 렌더한 예시입니다. 근거이며 판정이 아닙니다.</sub></p>

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

## 설계 방식

- Typed collector는 exhaustive status, stable `reason_code`, 관찰 범위, 근거, diagnostic을
  하나의 engine-owned exit policy까지 보존합니다.
- Sandbox에는 사용자 home이 아닌 생성된 decoy home이 들어가며, `store`만 모든 artifact를
  canonicalize하고 leak check한 뒤 atomic replace로 기록합니다.
- 두 언어 데모는 결정적으로 빌드되며 repository-owned browser asset만 불러옵니다.

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
