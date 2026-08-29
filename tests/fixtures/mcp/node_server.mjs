#!/usr/bin/env node
/** Deterministic clean MCP stdio fixture server. */

const MODES = ['file_read', 'host_connect', 'decoy_leak', 'idle_beacon', 'proc_exec'];
const ALL_MODES = [...MODES, ...MODES.map((mode) => `clean_${mode}`)];
const argv = process.argv.slice(2);
const mode = argv.find((argument) => !argument.startsWith('--'));
const era = argv.includes('--era=legacy') ? 'legacy' : 'modern';
const omitReady = argv.includes('--omit-ready');
const omitDeclaration = argv.includes('--omit-declaration');
if (!ALL_MODES.includes(mode)) process.exit(2);
const clean = mode.startsWith('clean_');
const tool = {
  name: mode,
  description: `Deterministic ${mode} fixture behavior`,
  inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  annotations: { readOnlyHint: clean },
  _meta: { panopticon: { complete: clean, paths: [], hosts: [], processes: [] } },
};

function send(value) {
  const body = Buffer.from(JSON.stringify(value));
  process.stdout.write(`Content-Length: ${body.length}\r\n\r\n`);
  process.stdout.write(body);
}

let pending = Buffer.alloc(0);
process.stdin.on('data', (chunk) => {
  pending = Buffer.concat([pending, chunk]);
  while (true) {
    let body;
    if (pending.subarray(0, 15).toString().toLowerCase() === 'content-length:') {
      const marker = pending.indexOf('\r\n\r\n');
      if (marker < 0) break;
      const match = pending.subarray(0, marker).toString().match(/^Content-Length:\s*(\d+)$/im);
      if (!match) break;
      const length = Number(match[1]);
      const end = marker + 4 + length;
      if (pending.length < end) break;
      body = pending.subarray(marker + 4, end);
      pending = pending.subarray(end);
    } else {
      const marker = pending.indexOf('\n');
      if (marker < 0) break;
      body = pending.subarray(0, marker);
      pending = pending.subarray(marker + 1);
    }
    let request;
    try {
      request = JSON.parse(body.toString('utf8'));
    } catch {
      continue;
    }
    const { method, id } = request;
    if (method === 'initialize') {
      send({
        jsonrpc: '2.0',
        id,
        result: {
          protocolVersion: era === 'legacy' ? '2024-11-05' : '2026-07-28',
          capabilities: { tools: {} },
          serverInfo: { name: 'panopticon-node-fixture', version: '1.0' },
        },
      });
      if (!omitReady) {
        send({
          jsonrpc: '2.0',
          method: 'notifications/fixture/ready',
          params: { mode },
        });
      }
    } else if (method === 'tools/list') {
      send({ jsonrpc: '2.0', id, result: { tools: omitDeclaration ? [] : [tool] } });
    } else if (method === 'tools/call') {
      const result = { mode, observed: clean ? 'none' : 'configured-by-python-fixture' };
      send({
        jsonrpc: '2.0',
        id,
        result: {
          content: [{ type: 'text', text: JSON.stringify(result) }],
          isError: false,
        },
      });
    } else if (method === 'shutdown') {
      send({ jsonrpc: '2.0', id, result: {} });
    } else if (method === 'exit') {
      process.exit(0);
    }
  }
});
