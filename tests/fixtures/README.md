# Fixtures

| dir | contents | epic |
|---|---|---|
| `discovery/<client>/` | clean, secret, broad_fs, duplicate, malformed, disabled, remote, variables configs | E02 |
| `mcp/evil/` | runnable stdio servers, one behavior class each: `file_read`, `host_connect`, `decoy_leak`, `idle_beacon`, `proc_exec` | E07/E12 |
| `mcp/clean/` | runnable stdio servers that must produce zero `confirmed` findings | E12 |
| `strace/` | recorded strace output + expected parsed events | E07 |
| `netlog/` | recorded proxy/DNS/iptables logs + expected events | E07 |
| `leak/` | payloads every persist path must reject (add to reach 20+) | E01 |
| `rules/<RULE-ID>/` | `positive_*.json`, `negative_*.json` RuleContext snapshots | E12 |
| `upstream/` | MCP-Sentinel vulnerable/clean fixtures and cassettes | E16 |
