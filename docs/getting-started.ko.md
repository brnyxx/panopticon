# Panopticon 시작하기

처음 설치하는 사용자가 MCP 하나를 로컬에서 관찰하고, 그 근거를 반복·비교·설명·정리할 수
있도록 전체 명령 흐름을 안내합니다. Panopticon은 관찰한 내용과 관찰하지 못한 범위를 함께
보고하며, 제품 판정으로 사용자의 판단을 대신하지 않습니다.

[English guide](getting-started.md) · [에이전트 실행 가이드](agent-guide.md) ·
[설치 및 릴리스 상세](release.md) · [개인정보와 외부 통신](privacy.md) ·
[제한 사항](limitations.md)

## 시작 전 준비

| 작업 | 필요한 것 |
|---|---|
| `doctor`로 설정된 MCP 찾기 | Claude Desktop, Claude Code, Cursor, VS Code, Windsurf 또는 명시적으로 설정한 generic source |
| `watch`로 로컬 MCP 관찰 | Linux/macOS에서 실행 중인 Docker 또는 Podman. Windows에서는 WSL2로 Linux 관찰 동작 사용 |
| 원격 MCP 관찰 | HTTP/SSE endpoint와 사용자가 명시적으로 선택한 header. 서버 쪽 파일·프로세스는 `UNSUPPORTED` |
| `scan`으로 MCP 저장소 분석 | 로컬 source tree. `--offline`이 없으면 standard/deep advisory 조회가 네트워크를 사용할 수 있음 |

현재 공개 릴리스는 PyPI, npm, GitHub, Homebrew 모두 **1.0.2**입니다.
`uv sync --all-extras`는 사용자 설치가 아니라 contributor setup입니다.

## 1. 설치 방법 하나 선택

### 한 번만 실행

```bash
uvx --from 'panopticon-mcp==1.0.2' pano version
uvx --from 'panopticon-mcp==1.0.2' pano doctor --offline
uvx --from 'panopticon-mcp==1.0.2' pano watch SERVER_NAME --offline
```

`uvx`는 호출할 때마다 임시 tool environment를 만듭니다.
이 가이드의 이후 명령마다 전체 `uvx --from ... pano` prefix를 사용합니다.

### 계속 사용할 설치

설치를 소유할 도구 하나를 선택합니다.

```bash
uv tool install panopticon-mcp==1.0.2
# 또는
pipx install panopticon-mcp==1.0.2
# 또는
npm install --global @brnyxx/panopticon@1.0.2
# 또는
brew install brnyxx/homebrew-tap/panopticon
```

관찰 전에 설치된 버전을 확인합니다.

```bash
pano version
```

공개 릴리스는 `pano 1.0.2 (schema 1.0)`을 출력합니다. Native archive, checksum, Sigstore,
폐쇄망 설치, upgrade, rollback은 [릴리스 가이드](release.md)에 있습니다.

패키지 설치는 선택한 package registry에 연결합니다. `pano --offline`은 Panopticon이 시작된
뒤의 외부 경로를 제어하며, 이미 수행한 패키지 설치를 폐쇄망 동작으로 바꾸지 않습니다.

## 2. 설정된 서버 찾기

먼저 읽기 전용 offline inventory를 실행합니다.

```bash
pano doctor --offline
```

기계가 읽는 출력은 다음과 같습니다.

```bash
pano doctor --offline --json
```

`doctor`에는 Docker나 Podman이 필요하지 않습니다. 지원 client discovery, installation
identity, configuration finding, exhaustive status, `reason_code`, diagnostic을 표시합니다.
검사 없이 client adapter 목록만 확인하려면 다음을 실행합니다.

```bash
pano doctor --list-clients --offline
```

출력에 실제로 나온 서버 이름 하나를 선택합니다. 예시의 `SERVER_NAME`은 바꿔 쓸 문자이며
셸 꺾쇠를 입력하지 않습니다.
두 installation의 이름이 같으면 `watch`는 `NAME_AMBIGUOUS`를 반환하며 `installation_id`를
지정할 수 없습니다. 어느 entry인지 추측하지 말고 멈춥니다.

## 3. 서버 하나 관찰

선택한 MCP 하나를 decoy sandbox에서 실행합니다.

```bash
pano watch SERVER_NAME --offline
```

자동화용 결과와 로컬 evidence card를 함께 만들려면 다음을 사용합니다.

```bash
pano watch SERVER_NAME --offline --json --png
```

기본값은 발견한 tool마다 한 번 호출하고 호출별 timeout은 20초입니다. 대상에 다른 bounded
run이 필요한 경우에만 `--calls`, `--timeout`을 조정합니다. 처음부터 `--all`을 쓰지 마세요.
서버 하나를 선택해야 실패와 근거를 정확히 귀속할 수 있습니다.

기본값에서는 설정된 실제 환경 변수 값을 sandbox에 전달하지 않습니다. `--real-env`,
`--real-env-all`, `--allow-destructive`는 대상이 받거나 수행할 범위를 넓힙니다. 정확한 대상과
목적을 검토한 뒤에만 사용합니다. 실제 환경 변수 옵션으로 전달한 값은 persisted artifact에
기록되지 않고 거부됩니다.

Offline local observation은 digest가 고정된 sandbox image가 이미 있어야 하며 DNS/proxy
egress observer를 시작하지 않습니다. 따라서 network coverage를 침묵으로 추론하지 않고
명시적으로 남깁니다. Connected local observation은 proxy/DNS 시도를 기록하고 proxied target
traffic을 허용할 수 있습니다. Connected mode를 선택하기 전에
[connected/offline 경계](privacy.md#connected-and-offline-observation)를 읽으세요.

### Offline watch용 image 준비

깨끗한 runtime에서는 offline observation 전에 별도 승인을 받아 GHCR에 한 번 연결합니다.
다음 명령은 MCP를 실행하지 않고 1.0.2가 선택할 수 있는 immutable image를 모두 준비합니다.

```bash
RUNTIME=docker  # 또는 podman
$RUNTIME pull ghcr.io/brnyxx/pano-sandbox-base:0.1@sha256:0b88136f67f67f463ac1e9cc531dbe1bad7ea95d5ad5e4afd68337b966e24249
$RUNTIME pull ghcr.io/brnyxx/pano-sandbox-node:20@sha256:2ef58b44bd9ebc247e97d1b3c54f63570ae206b925b277d86d93e5319d1cd367
$RUNTIME pull ghcr.io/brnyxx/pano-sandbox-node:22@sha256:d0f7cc3fcac6a24ea0f8b7b9d62c542a04642ca5b38a4e249e017a7311a8b7c5
$RUNTIME pull ghcr.io/brnyxx/pano-sandbox-python:3.12@sha256:3e2b99433c18506f59d0e44e40b8af2b0350ee4df903252a1ab462f0eac3f589
```

네 pull은 `ghcr.io`에 연결하며 `--offline`은 이 연결을 승인하거나 수행하지 않습니다.
Digest는 `src/panopticon/sandbox/images.lock`의 runtime trust value입니다. Image가 local에
있으면 `watch --offline`은 image를 pull하거나 connected DNS/proxy egress service를 시작하지
않습니다. 필요한 image가 없으면 target 실행 전에 `IMAGE_NOT_PRESENT`로 멈춥니다.

## 4. 결과를 정확히 읽기

결과는 stage status, stable `reason_code`, coverage dimension, evidence, finding, diagnostic을
함께 제공합니다. 하나만 떼어 판정하지 않습니다.

| 상태 | 의미 | 운영자 조치 |
|---|---|---|
| `COMPLETE` | 요청한 stage가 표시된 coverage로 완료됨 | 근거와 declared scope를 검토. 미래의 미관찰 동작에 대한 주장이 아님 |
| `PARTIAL` | 일부 작업만 완료되고 coverage가 남음 | 결론 전에 coverage와 diagnostic 확인 |
| `INCOMPLETE` | 필요한 작업을 모두 마치지 못함 | `reason_code`를 해결한 뒤 같은 bounded command 재실행 |
| `FAILED` | stage에서 runtime failure 발생 | 재시도 전에 diagnostic과 runtime 확인 |
| `UNSUPPORTED` | 플랫폼·모드·대상이 해당 dimension을 제공하지 못함 | UNKNOWN으로 유지하거나 지원 환경 선택 |
| `SKIPPED` | stage를 의도적으로 실행하지 않음 | 근거로 해석하지 않음 |
| `NOT_REQUESTED` | command가 stage를 요청하지 않음 | 필요한 경우 명시적으로 요청 |
| `UNKNOWN` | 현재 근거로 결론을 낼 수 없음 | 보고와 판단에 불확실성을 그대로 유지 |

Stable rule ID로 finding을 설명합니다.

```bash
pano explain WATCH-003
pano explain WATCH-003 --lang ko
```

## 5. 첫 관찰 이후

| 목표 | 명령 | 설명 |
|---|---|---|
| 비교 기준 저장 | `pano baseline create --label first-observation` | 하나의 installation에 대한 canonical evidence 저장 |
| baseline 목록 | `pano baseline list` | 자동화는 `--json` 사용 |
| baseline과 비교 | `pano diff SERVER_NAME --since auto` | semantic input이 같으면 diff가 비어 있음 |
| MCP source 빠른 분석 | `pano scan . --mode quick --offline` | 외부 제품 조회 없는 static analysis |
| dependency advisory 포함 | `pano scan . --mode standard` | source가 아니라 exact locked package coordinate를 OSV로 보냄 |
| 사용자 호출 semantic reviewer | `pano scan . --mode deep` | payload disclosure를 표시하고 사용자 key로 redacted excerpt 전송 |
| 저장소 CI policy 실행 | `pano ci . --mode standard --fail-on high` | SARIF를 쓰고 문서화된 exit policy 적용 |
| 설정 변경 preview | `pano fix SERVER_NAME --dry-run --offline` | diff 검토 후 별도 `--yes` 호출로 적용 |
| 기록된 fix undo | `pano fix --undo TRANSACTION_ID` | transaction 뒤 파일이 바뀌면 거부 |
| 설치된 MCP wrapper preview | `pano install CLIENT --dry-run` | `_pano_original`에 원래 command 보존. 검토 뒤 적용 |
| wrapper 복원 preview | `pano uninstall CLIENT --dry-run` | preview 후 별도 검토를 거쳐 `--yes` 사용 |

## Script와 agent용 exit code

| 코드 | 의미 |
|---:|---|
| `0` | policy 또는 required-coverage 종료 조건 없이 완료 |
| `1` | 선택한 failure threshold에 해당하는 policy finding |
| `2` | 사용법 오류 |
| `3` | required coverage 불완전 |
| `4` | configuration 오류 |
| `5` | runtime failure 또는 필요한 runtime 미지원 |
| `64` | 해당 build에서 command surface가 아직 구현되지 않음 |

Nonzero exit를 success로 바꾸지 않습니다. 재시도·환경 변경·중단을 결정하기 전에 JSON의
`status`, `reason_code`, `coverage`, finding, diagnostic을 읽습니다.

## 로컬 산출물과 정리

`~/.panopticon/`은 mode `0700`으로 생성되며 observation, baseline, wrap record, cache, fix
journal, backup을 보관합니다. 모든 persistence path는 쓰기 전에 canonicalize와 leak check를
거칩니다.
`watch` terminal receipt는 `Artifact:`를 출력하고 JSON은 `artifact_path`를 반환합니다.
Observation-list command가 없으므로 이 경로를 보관하세요. 값은 `~/.panopticon/` 기준의
상대 경로이며 보통 `observations/...json`입니다. `--png`가 성공하면 해당 JSON의
`observation_id`를 읽으세요. 별도 card는 `~/.panopticon/cards/OBSERVATION_ID.png`입니다.

개별 baseline은 다음과 같이 확인하고 제거합니다.

```bash
pano baseline list
pano baseline rm BASELINE_ID
```

Journal이나 backup을 지우기 전에 configuration change를 복원합니다. Panopticon에는 bulk
삭제 명령이 없습니다. Active writer를 멈추고 설정을 복원한 뒤 OS file tool로 선택한 artifact를
지우거나 `~/.panopticon/`을 제거해 모든 로컬 evidence와 cache를 정리합니다. 정확한 저장·외부
통신·정리 계약은 [privacy.md](privacy.md)에 있습니다.

## 문제 해결

- **서버가 나오지 않음:** `pano doctor --list-clients --offline`을 실행하고, intended client가
  configuration을 소유하는지 확인한 뒤 추측한 다른 서버 이름 없이 `doctor`를 다시 실행합니다.
- **`RUNTIME_UNAVAILABLE`:** Docker 또는 Podman을 시작하고 명시적 선택이 필요하면
  `--runtime docker` 또는 `--runtime podman`으로 다시 실행합니다.
- **`TIMEOUT`:** 먼저 tool과 target을 확인하고, 무제한 재시도 대신 bounded `--timeout`만
  늘립니다.
- **원격 file/process가 `UNSUPPORTED`:** remote observation boundary이며 local observation
  성공을 뜻하지 않습니다.
- **persisted artifact 거부:** 요청한 persistence path에서 실제 token, 실제 home path,
  real-environment value를 제거합니다. Leak check를 끄지 않습니다.

## 제품 설계

Architecture는 CLI parsing, engine result, collector, reporter, 유일한 persistence gateway를
분리합니다. Status와 reason은 boundary에서 typed value이며 reporter가 다시 판정하지 않습니다.
Sandbox에는 사용자 home이 아니라 decoy home이 들어갑니다. Static demo는 local asset과
결정적 bilingual builder를 사용하며 browser analytics나 storage가 없습니다.

[ARCHITECTURE.md](../ARCHITECTURE.md), [DESIGN.md](../DESIGN.md),
[decision log](DECISIONS.md), [agent 실행 가이드](agent-guide.md)에서 이 선택의 계약을 확인할
수 있습니다.
