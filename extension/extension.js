/* eslint-disable no-undef */
"use strict";

const vscode = require("vscode");
const http = require("http");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");

const VIEW_TYPE = "tencentDocument.present";
const DEFAULT_PORT = 39110;

/** @type {import('child_process').ChildProcess | null} */
let daemonProc = null;

function getPort() {
  const cfg = vscode.workspace.getConfiguration("tencentDocument");
  const n = cfg.get("previewPort");
  return typeof n === "number" && n > 0 ? n : DEFAULT_PORT;
}

function getPluginRoot(context) {
  const cfg = vscode.workspace.getConfiguration("tencentDocument");
  const fromCfg = String(cfg.get("pluginRoot") || "").trim();
  if (fromCfg && fs.existsSync(fromCfg)) return fromCfg;

  const home = process.env.HOME || process.env.USERPROFILE || "";
  const candidates = [
    path.join(home, ".cursor", "plugins", "local", "tencent-document-editor"),
    path.resolve(context.extensionPath, ".."),
    path.resolve(context.extensionPath, "..", "..", "plugins", "local", "tencent-document-editor"),
  ];
  for (const c of candidates) {
    if (c && fs.existsSync(path.join(c, "mcp-server", "preview_daemon.py"))) return c;
  }
  return "";
}

function detectFormat(fsPath) {
  const ext = path.extname(fsPath).toLowerCase();
  if (ext === ".html" || ext === ".htm") return "html";
  return "md";
}

function presentUrl(fsPath, port) {
  const fmt = detectFormat(fsPath);
  const q = new URLSearchParams({ path: fsPath, format: fmt });
  return `http://127.0.0.1:${port}/edit?${q.toString()}`;
}

function portOpen(port) {
  return new Promise((resolve) => {
    const req = http.get({ host: "127.0.0.1", port, path: "/health", timeout: 400 }, (res) => {
      res.resume();
      resolve(true);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function ensureDaemon(pluginRoot, port) {
  if (await portOpen(port)) return true;
  if (!pluginRoot) {
    vscode.window.showErrorMessage(
      "Document Present: 未找到插件目录。请运行 bash plugin/scripts/install-local.sh"
    );
    return false;
  }
  const daemon = path.join(pluginRoot, "mcp-server", "preview_daemon.py");
  if (!fs.existsSync(daemon)) {
    vscode.window.showErrorMessage(`Document Present: 缺少 ${daemon}`);
    return false;
  }
  const logDir = "/tmp/document_preview_logs";
  try {
    fs.mkdirSync(logDir, { recursive: true });
  } catch (_) {
    /* ignore */
  }
  const logPath = path.join(logDir, "preview_daemon.log");
  const logFd = fs.openSync(logPath, "a");
  daemonProc = spawn("python3", [daemon], {
    env: { ...process.env, DOCUMENT_PREVIEW_PORT: String(port) },
    detached: true,
    stdio: ["ignore", logFd, logFd],
  });
  daemonProc.unref();
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 150));
    if (await portOpen(port)) return true;
  }
  vscode.window.showErrorMessage(`Document Present: 预览服务未就绪（端口 ${port}）。日志: ${logPath}`);
  return false;
}

function escapeJs(s) {
  return JSON.stringify(String(s));
}

/** HTTP helper from extension host (webview cannot reach localhost). */
function httpJson(port, method, reqPath, bodyText, headers) {
  return new Promise((resolve, reject) => {
    const payload = bodyText != null ? Buffer.from(bodyText, "utf8") : null;
    const opts = {
      host: "127.0.0.1",
      port,
      path: reqPath,
      method: method || "GET",
      headers: Object.assign(
        {
          Accept: "application/json",
        },
        headers || {},
        payload
          ? {
              "Content-Type": (headers && headers["Content-Type"]) || "application/json",
              "Content-Length": String(payload.length),
            }
          : {}
      ),
      timeout: 12000,
    };
    const req = http.request(opts, (res) => {
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => {
        const raw = Buffer.concat(chunks).toString("utf8");
        try {
          resolve(JSON.parse(raw || "{}"));
        } catch (e) {
          reject(new Error(`bad json from ${reqPath}: ${raw.slice(0, 200)}`));
        }
      });
    });
    req.on("error", reject);
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("http timeout"));
    });
    if (payload) req.write(payload);
    req.end();
  });
}

function buildEmbeddedPresentHtml(pluginRoot, fsPath, port) {
  const uiPath = path.join(pluginRoot, "mcp-server", "present_ui.html");
  if (!fs.existsSync(uiPath)) {
    return null;
  }
  let html = fs.readFileSync(uiPath, "utf8");
  const fmt = detectFormat(fsPath);
  const base = `http://127.0.0.1:${port}`;
  // bridge: true tells UI to use postMessage (fetch to localhost is blocked in Cursor webview)
  const boot = `<script>
window.__PRESENT__ = { path: ${escapeJs(fsPath)}, format: ${escapeJs(fmt)}, base: ${escapeJs(base)}, bridge: true };
window.__vscode = acquireVsCodeApi();
</script>`;
  const csp = [
    "default-src 'none'",
    "img-src data: blob: http://127.0.0.1:* http://localhost:*",
    "style-src 'unsafe-inline'",
    "script-src 'unsafe-inline'",
    "font-src data:",
  ].join("; ");
  if (/<meta\s+http-equiv=["']Content-Security-Policy["']/i.test(html)) {
    html = html.replace(
      /<meta\s+http-equiv=["']Content-Security-Policy["'][^>]*>/i,
      `<meta http-equiv="Content-Security-Policy" content="${csp}"/>`
    );
  } else {
    html = html.replace(/<head>/i, `<head>\n<meta http-equiv="Content-Security-Policy" content="${csp}"/>`);
  }
  if (/<head[^>]*>/i.test(html)) {
    html = html.replace(/<head[^>]*>/i, (m) => m + "\n" + boot);
  } else {
    html = boot + html;
  }
  return html;
}

/**
 * @implements {vscode.CustomReadonlyEditorProvider}
 */
class PresentEditorProvider {
  /** @param {vscode.ExtensionContext} context */
  constructor(context) {
    this.context = context;
  }

  async openCustomDocument(uri) {
    return { uri, dispose() {} };
  }

  async resolveCustomEditor(document, webviewPanel) {
    const fsPath = document.uri.fsPath;
    const port = getPort();
    const pluginRoot = getPluginRoot(this.context);
    const ok = await ensureDaemon(pluginRoot, port);
    const url = presentUrl(fsPath, port);

    webviewPanel.webview.options = { enableScripts: true };

    let html = null;
    if (ok && pluginRoot) {
      html = buildEmbeddedPresentHtml(pluginRoot, fsPath, port);
    }

    if (html) {
      webviewPanel.webview.html = html;
    } else if (ok) {
      try {
        await vscode.commands.executeCommand("simpleBrowser.show", url);
      } catch (_) {
        /* ignore */
      }
      webviewPanel.webview.html = `<!DOCTYPE html><html><body style="font:13px/1.5 -apple-system,sans-serif;padding:16px">
        <p>请用 Simple Browser 打开：</p>
        <p><a href="${url}">${url}</a></p>
        <button id="src">编辑源码</button>
        <script>
          const vscode = acquireVsCodeApi();
          document.getElementById('src').onclick = () => vscode.postMessage({ type: 'openSource' });
        </script>
      </body></html>`;
    } else {
      webviewPanel.webview.html = `<!DOCTYPE html><html><body style="font-family:sans-serif;padding:16px">
        <p>预览服务未启动。请运行 install-local.sh 后 Reload Window。</p>
      </body></html>`;
    }

    webviewPanel.webview.onDidReceiveMessage(async (msg) => {
      if (!msg || !msg.type) return;
      if (msg.type === "openSource") {
        await vscode.commands.executeCommand("vscode.openWith", document.uri, "default");
        return;
      }
      if (msg.type === "api") {
        try {
          const data = await httpJson(port, msg.method || "GET", msg.path, msg.body, msg.headers);
          webviewPanel.webview.postMessage({ type: "apiResult", id: msg.id, ok: true, data });
        } catch (e) {
          webviewPanel.webview.postMessage({
            type: "apiResult",
            id: msg.id,
            ok: false,
            error: String((e && e.message) || e),
          });
        }
        return;
      }
      if (msg.type === "upload") {
        try {
          const docPath = msg.path || fsPath;
          const baseDir = path.dirname(docPath);
          let name = path.basename(msg.filename || "upload.bin");
          name = name.replace(/[^\w.\-+]/g, "_") || "upload.bin";
          const dest = path.join(baseDir, name);
          const buf = Buffer.from(msg.base64 || "", "base64");
          fs.writeFileSync(dest, buf);
          const mediaUrl = `/media/${encodeURIComponent(dest)}`;
          // Prefer absolute media URL for webview img (relative /media won't resolve)
          const absUrl = `http://127.0.0.1:${port}${mediaUrl}`;
          webviewPanel.webview.postMessage({
            type: "apiResult",
            id: msg.id,
            ok: true,
            data: { ok: true, path: dest, name, url: absUrl, bytes: buf.length },
          });
        } catch (e) {
          webviewPanel.webview.postMessage({
            type: "apiResult",
            id: msg.id,
            ok: false,
            error: String((e && e.message) || e),
          });
        }
      }
    });
  }
}

async function ensureEditorAssociations() {
  const cfg = vscode.workspace.getConfiguration("workbench");
  const current = Object.assign({}, cfg.get("editorAssociations") || {});
  const want = {
    "*.html": VIEW_TYPE,
    "*.htm": VIEW_TYPE,
    "*.md": VIEW_TYPE,
    "*.markdown": VIEW_TYPE,
  };
  let changed = false;
  for (const [k, v] of Object.entries(want)) {
    if (current[k] !== v) {
      current[k] = v;
      changed = true;
    }
  }
  if (changed) {
    try {
      await cfg.update("editorAssociations", current, vscode.ConfigurationTarget.Global);
    } catch (_) {
      /* ignore */
    }
  }
}

/** @param {vscode.ExtensionContext} context */
function activate(context) {
  ensureEditorAssociations();

  const provider = new PresentEditorProvider(context);
  context.subscriptions.push(
    vscode.window.registerCustomEditorProvider(VIEW_TYPE, provider, {
      webviewOptions: { retainContextWhenHidden: true },
      supportsMultipleEditorsPerDocument: false,
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("tencentDocument.openPresent", async (uri) => {
      const target = uri || vscode.window.activeTextEditor?.document?.uri;
      if (!target) {
        vscode.window.showWarningMessage("Document Present: 没有选中文件");
        return;
      }
      await vscode.commands.executeCommand("vscode.openWith", target, VIEW_TYPE);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("tencentDocument.openSource", async (uri) => {
      let u = uri || vscode.window.activeTextEditor?.document?.uri;
      if (!u) {
        const tab = vscode.window.tabGroups.activeTabGroup.activeTab;
        if (tab && tab.input && tab.input.uri) u = tab.input.uri;
      }
      if (!u) {
        vscode.window.showWarningMessage("Document Present: 没有选中文件");
        return;
      }
      await vscode.commands.executeCommand("vscode.openWith", u, "default");
    })
  );
}

function deactivate() {
  daemonProc = null;
}

module.exports = { activate, deactivate };
