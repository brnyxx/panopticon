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
