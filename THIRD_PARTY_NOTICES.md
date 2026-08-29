Third-party notices — Panopticon
Copyright (c) 2026 Panopticon contributors

MCP-Sentinel
Repository: https://github.com/BashaarJavaid/MCP-Sentinel
Pinned commit: e717e955210b1d2a3e9fb1cdc266587c77ffebf3
License: MIT
Copyright (c) 2026 MCP Sentinel contributors

Panopticon contains two clearly separated forms of MCP-Sentinel material:
- byte-exact replay sources, tests, fixtures, schemas, and assets under tests/upstream/;
- typed product adaptations under src/panopticon/analyzers/static,
  src/panopticon/analyzers/semantic, and src/panopticon/analyzers/dependency.

The canonical per-file source and destination checksums are recorded in
vendor/mcp-sentinel-e717e955.json. The test-only replay package is excluded from
Panopticon wheels. Product adaptations do not expose the upstream `sentinel`
package namespace and do not include the upstream dynamic probe as product code.

NanumGothic Regular
Source: https://github.com/google/fonts/tree/16680f8688ffcd467d2eb2146a9ce0343404581d/ofl/nanumgothic
Pinned commit: 16680f8688ffcd467d2eb2146a9ce0343404581d
SHA-256: 76f45ef4a6bcff344c837c95a7dcc26e017e38b5846d5ae0cdcb5b86be2e2d31
License: SIL Open Font License 1.1
Copyright (c) 2010, NHN Corporation

The unmodified font and its complete license are bundled under
src/panopticon/badge/assets/.

Model Context Protocol server-everything fixture
Repository: https://github.com/modelcontextprotocol/servers
Package: @modelcontextprotocol/server-everything 2026.8.18
Source commit: 644cbe65648f1d6c687b3b647683e1aaa4ed1eba
Registry SHA-256: bd11de97a2413c7083f7a9252be55d0d9bfbdb67b2531dbe4217a6517226d36d
License: Apache-2.0/MIT transition terms in tests/fixtures/mcp/official/LICENSE

The unmodified registry archive is test-only and is excluded from Panopticon
wheels.

Official MCP server availability audit
--------------------------------------
The official server set is recorded in
`tests/fixtures/mcp/official/manifest.json`. Filesystem, memory, and fetch are
pinned to the current official repository commit
`cda92bdaacd558192fedf1a60d2bb27510792388`. GitHub and SQLite are pinned to the
archived official commit `1f705677a930ec618b7a16d87d00cee7db747ff2`.
The npm SHA-512 values are retained for the package-backed entries; source-only
entries identify their immutable GitHub tree directly. Network acquisition is
never implicit: `scripts/vendor_upstream.py` vendors audited source, while
`scripts/verify_official_examples.py` clones the two exact commits into a
temporary directory, builds them from their lockfiles, executes every advertised
tool through Panopticon, and deletes the directory. The GitHub run uses the
deterministic in-memory fetch fixture and a synthetic token, so it cannot mutate
GitHub or use a personal credential.

MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
