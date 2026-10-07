#!/usr/bin/env node
/**
 * WorkBuddy-style guest bootstrap for Cursor/VS Code.
 *
 * WorkBuddy loads bare editor_sdk and attaches Electron preload
 * (tdoc-preview-preload.js) that exposes mqq + __WB_DOCS_FEATURE_LIST__.
 * VS Code iframes cannot use that preload, so this proxy:
 *   - public :EDITOR_SDK_PORT (39099) → upstream editor_sdk :UPSTREAM (39101)
 *   - full WebSocket Upgrade tunnel (required for guest load)
 *   - injects mqq_inject.js into static pc.html responses only
 *
 * No npm deps — Node stdlib only.
 */
"use strict";

const http = require("http");
const net = require("net");
const fs = require("fs");
const path = require("path");

const PUBLIC_PORT = Number(process.env.EDITOR_SDK_PORT || 39099);
const UPSTREAM_PORT = Number(process.env.EDITOR_SDK_UPSTREAM_PORT || 39101);
const ROOT = __dirname;


function loadInjectTag() {
  // Match sdk_port_proxy: mqq shim + DOM float AI (native confirm may not call mqq).
  const parts = ["mqq_inject.js", "float_toolbar_ai.js"].map((name) => {
    const p = path.join(ROOT, name);
    return fs.existsSync(p) ? fs.readFileSync(p) : Buffer.alloc(0);
  });
  const body = Buffer.concat([
    Buffer.from("(function(){\n"),
    parts[0],
    Buffer.from("\n;\n"),
    parts[1],
    Buffer.from("\n})();\n"),
  ]);
  return Buffer.concat([
    Buffer.from('<script data-hermes-mqq="1">\n'),
    body,
    Buffer.from("\n</script>"),
  ]);
}

let INJECT_TAG = null;
function injectTag() {
  if (!INJECT_TAG) INJECT_TAG = loadInjectTag();
  return INJECT_TAG;
}

function prepareHtml(buf) {
  if (buf.includes("data-hermes-mqq") || buf.includes("hermes-tencent-doc-mqq")) {
    return buf;
  }
  const tag = injectTag();
  const lower = buf.toString("latin1").toLowerCase();
  const idx = lower.indexOf("<head");
  if (idx >= 0) {
    const gt = buf.indexOf(0x3e, idx); // '>'
    if (gt >= 0) {
      return Buffer.concat([buf.subarray(0, gt + 1), tag, buf.subarray(gt + 1)]);
    }
  }
  return Buffer.concat([tag, buf]);
}

function shouldInject(reqPath, contentType) {
  const pathOnly = String(reqPath || "").split("?", 1)[0];
  if (pathOnly.endsWith("pc.html")) return true;
  return String(contentType || "")
    .toLowerCase()
    .includes("text/html");
}

function filterOutHeaders(headers, { dropLength }) {
  const out = { ...headers };
  delete out["content-encoding"];
  if (dropLength) delete out["content-length"];
  // Keep transfer-encoding for streamed responses; drop when we recompute length.
  if (dropLength) delete out["transfer-encoding"];
  out["access-control-allow-origin"] = "*";
  return out;
}

function proxyHttp(clientReq, clientRes) {
  const headers = { ...clientReq.headers, host: `127.0.0.1:${UPSTREAM_PORT}` };
  // Only strip encoding when we may need to rewrite HTML body.
  const pathOnly = String(clientReq.url || "").split("?", 1)[0];
  const maybeHtml = pathOnly.endsWith("pc.html");
  if (maybeHtml) delete headers["accept-encoding"];

  const upReq = http.request(
    {
      host: "127.0.0.1",
      port: UPSTREAM_PORT,
      path: clientReq.url,
      method: clientReq.method,
      headers,
    },
    (upRes) => {
      const ctype = String(upRes.headers["content-type"] || "");
      const injected = shouldInject(clientReq.url, ctype);
      const isSSE =
        ctype.toLowerCase().includes("text/event-stream") ||
        String(clientReq.headers.accept || "")
          .toLowerCase()
          .includes("text/event-stream");

      // CRITICAL: local_edit_service uses EventSource (SSE). Must stream, never buffer.
      // Only buffer pc.html (and other HTML) so we can inject mqq / feature list.
      if (!injected) {
        const outHeaders = filterOutHeaders(upRes.headers, { dropLength: false });
        clientRes.writeHead(upRes.statusCode || 200, outHeaders);
        upRes.pipe(clientRes);
        return;
      }

      const chunks = [];
      upRes.on("data", (c) => chunks.push(c));
      upRes.on("end", () => {
        let body = prepareHtml(Buffer.concat(chunks));
        const outHeaders = filterOutHeaders(upRes.headers, { dropLength: true });
        outHeaders["content-length"] = String(body.length);
        outHeaders["content-type"] = "text/html; charset=utf-8";
        clientRes.writeHead(upRes.statusCode || 200, outHeaders);
        clientRes.end(body);
      });
    }
  );
  upReq.on("error", (err) => {
    if (!clientRes.headersSent) {
      clientRes.writeHead(502, { "Content-Type": "application/json" });
    }
    clientRes.end(
      JSON.stringify({
        ok: false,
        error: `upstream :${UPSTREAM_PORT} unreachable: ${err.message}`,
      })
    );
  });
  clientReq.pipe(upReq);
}

function pipeSockets(a, b) {
  a.pipe(b);
  b.pipe(a);
  const closeBoth = () => {
    try {
      a.destroy();
    } catch (_) {}
    try {
      b.destroy();
    } catch (_) {}
  };
  a.on("error", closeBoth);
  b.on("error", closeBoth);
  a.on("close", closeBoth);
  b.on("close", closeBoth);
}

function proxyUpgrade(req, socket, head) {
  const pathOnly = String(req.url || "").split("?", 1)[0];
  const up = net.connect(UPSTREAM_PORT, "127.0.0.1", () => {
    // Rebuild HTTP Upgrade request to upstream
    const lines = [`${req.method} ${req.url} HTTP/1.1`];
    for (const [k, v] of Object.entries(req.headers)) {
      if (v == null) continue;
      const val = k.toLowerCase() === "host" ? `127.0.0.1:${UPSTREAM_PORT}` : v;
      if (Array.isArray(val)) {
        for (const item of val) lines.push(`${k}: ${item}`);
      } else {
        lines.push(`${k}: ${val}`);
      }
    }
    up.write(lines.join("\r\n") + "\r\n\r\n");
    if (head && head.length) up.write(head);
    pipeSockets(socket, up);
  });
  up.on("error", (err) => {
    try {
      socket.write("HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n");
    } catch (_) {}
    try {
      socket.destroy();
    } catch (_) {}
  });
  socket.on("error", (err) => {
    try {
      up.destroy();
    } catch (_) {}
  });
  socket.on("close", () => {
  });
}

function main() {
  const server = http.createServer((req, res) => {
    if (req.method === "OPTIONS") {
      res.writeHead(204, {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET,POST,PUT,HEAD,OPTIONS",
        "Access-Control-Allow-Headers": "*",
      });
      res.end();
      return;
    }
    proxyHttp(req, res);
  });

  server.on("upgrade", proxyUpgrade);

  server.listen(PUBLIC_PORT, "127.0.0.1", () => {
    console.log(
      `[sdk_inject_proxy] public=:${PUBLIC_PORT} upstream=:${UPSTREAM_PORT} mqq+ws`
    );
  });

  server.on("error", (err) => {
    console.error("[sdk_inject_proxy] listen failed:", err.message);
    process.exit(1);
  });
}

main();
