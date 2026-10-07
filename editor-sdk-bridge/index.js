#!/usr/bin/env node
/**
 * Thin Node bridge that shells to the Python document bridge.
 * Canonical logic lives in ../mcp-server/bridge.py (editor_sdk HTTP MCP).
 *
 * Usage:
 *   node index.js preview /abs/path/file.md
 *   node index.js edit /abs/path/out.docx --format docx --content-format md <<'EOF'
 *   # Title
 *   body
 *   EOF
 *   node index.js convert /abs/a.md --to html
 *   node index.js status
 */
'use strict';

const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const BRIDGE = path.join(ROOT, 'mcp-server', 'cli.py');

function run(args, input) {
  const env = Object.assign({}, process.env, {
    DOCUMENT_EDITOR_PLUGIN_ROOT: ROOT,
  });
  if (!env.EDITOR_SDK_BIN) {
    const cand = path.resolve(
      ROOT,
      '../third_party/tencent-editor-sdk/darwin-arm64/editor_sdk'
    );
    if (fs.existsSync(cand)) env.EDITOR_SDK_BIN = cand;
  }
  const res = spawnSync('python3', [BRIDGE, ...args], {
    env,
    encoding: 'utf8',
    input: input || undefined,
    maxBuffer: 20 * 1024 * 1024,
  });
  if (res.stdout) process.stdout.write(res.stdout);
  if (res.stderr) process.stderr.write(res.stderr);
  process.exit(res.status == null ? 1 : res.status);
}

function usage() {
  console.error(`Usage:
  node index.js preview <file> [--format md|html|docx|pptx|xlsx|pdf]
  node index.js edit <file> [--format ...] [--content-format md|html] [--content "..."]
  node index.js convert <file> --to <fmt> [--output path]
  node index.js status`);
  process.exit(2);
}

const argv = process.argv.slice(2);
if (!argv.length) usage();

const cmd = argv[0];
if (cmd === 'preview') {
  const file = argv[1];
  if (!file) usage();
  const args = ['preview', file];
  const fi = argv.indexOf('--format');
  if (fi >= 0 && argv[fi + 1]) args.push('--format', argv[fi + 1]);
  run(args);
} else if (cmd === 'edit') {
  const file = argv[1];
  if (!file) usage();
  const args = ['edit', file];
  const fi = argv.indexOf('--format');
  if (fi >= 0 && argv[fi + 1]) args.push('--format', argv[fi + 1]);
  const ci = argv.indexOf('--content-format');
  if (ci >= 0 && argv[ci + 1]) args.push('--content-format', argv[ci + 1]);
  const xi = argv.indexOf('--content');
  let input = null;
  if (xi >= 0 && argv[xi + 1]) {
    args.push('--content', argv[xi + 1]);
  } else if (!process.stdin.isTTY) {
    input = fs.readFileSync(0, 'utf8');
    args.push('--stdin');
  } else {
    usage();
  }
  run(args, input);
} else if (cmd === 'convert') {
  const file = argv[1];
  const ti = argv.indexOf('--to');
  if (!file || ti < 0 || !argv[ti + 1]) usage();
  const args = ['convert', file, '--to', argv[ti + 1]];
  const oi = argv.indexOf('--output');
  if (oi >= 0 && argv[oi + 1]) args.push('--output', argv[oi + 1]);
  run(args);
} else if (cmd === 'status') {
  run(['status']);
} else {
  usage();
}
