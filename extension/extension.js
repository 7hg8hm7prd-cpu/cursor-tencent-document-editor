/* eslint-disable no-undef */
"use strict";

const vscode = require("vscode");
const http = require("http");
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const { spawn } = require("child_process");

const VIEW_TYPE = "tencentDocument.present";
const DEFAULT_PORT = 39110;
const DEFAULT_SDK_PORT = 39099;

/** @type {import('child_process').ChildProcess | null} */
let daemonProc = null;

const OFFICE_EXT = {
  ".docx": "doc",
  ".doc": "doc",
  ".wps": "doc",
  ".xlsx": "sheet",
  ".xls": "sheet",
  ".csv": "sheet",
  ".pptx": "slide",
  ".ppt": "slide",
  ".pdf": "pdf",
};

function getPort() {
  const cfg = vscode.workspace.getConfiguration("tencentDocument");
  const n = cfg.get("previewPort");
  return typeof n === "number" && n > 0 ? n : DEFAULT_PORT;
}

function getSdkPort() {
  const cfg = vscode.workspace.getConfiguration("tencentDocument");
  const n = cfg.get("sdkPort");
  if (typeof n === "number" && n > 0) return n;
  const env = Number(process.env.EDITOR_SDK_PORT || 0);
  return env > 0 ? env : DEFAULT_SDK_PORT;
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
  if (OFFICE_EXT[ext] === "doc") return "docx";
  if (OFFICE_EXT[ext] === "sheet") return "xlsx";
  if (OFFICE_EXT[ext] === "slide") return "pptx";
  if (OFFICE_EXT[ext] === "pdf") return "pdf";
  return "md";
}

function isOfficePath(fsPath) {
  return Boolean(OFFICE_EXT[path.extname(fsPath).toLowerCase()]);
}

/** WorkBuddy-compatible editor_sdk visual URL. */
function buildSdkPreviewUrl(fsPath, sdkPort) {
  const ext = path.extname(fsPath).toLowerCase();
  const type = OFFICE_EXT[ext];
  if (!type) return "";
  const mode = type === "pdf" ? "readonly" : "edit";
  const globalPadId = crypto.createHash("md5").update(fsPath).digest("hex");
  const params = new URLSearchParams({
    title: path.basename(fsPath),
    localFilePath: fsPath,
    globalPadId,
  });
  if (type === "doc") {
    params.set("local_edit", "1");
    params.set("client", "sdk_local");
    params.set("mode", mode === "readonly" ? "readonly" : "edit");
    params.set("toolbar", mode === "readonly" ? "hide" : "show");
    params.set("outline", "show");
    params.set("statusbar", mode === "readonly" ? "hide" : "show");
    params.set("editorSdkUrl", `http://127.0.0.1:${sdkPort}`);
  } else if (type === "sheet") {
    params.set("local_edit", "1");
    params.set("client", "sdk_local_pure");
    params.set("mode", mode === "readonly" ? "readonly" : "edit");
  } else if (type === "slide") {
    params.set("local_edit", "1");
    params.set("client", mode === "readonly" ? "sdk_local_preview" : "sdk_local_wb");
    params.set("hideTitlebar", "1");
  }
  return `http://127.0.0.1:${sdkPort}/static/${type}/pc.html?${params.toString()}`;
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

/** Start editor_sdk via ensure_sdk.py if /health is down. */
async function ensureSdk(pluginRoot, sdkPort) {
  if (await portOpen(sdkPort)) return true;
  if (!pluginRoot) {
    vscode.window.showErrorMessage(
      "Document Present: 未找到插件目录，无法启动 editor_sdk。"
    );
    return false;
  }
  const ensurePy = path.join(pluginRoot, "mcp-server", "ensure_sdk.py");
  if (!fs.existsSync(ensurePy)) {
    vscode.window.showErrorMessage(`Document Present: 缺少 ${ensurePy}`);
    return false;
  }
  await new Promise((resolve) => {
    const child = spawn("python3", [ensurePy], {
      env: {
        ...process.env,
        EDITOR_SDK_PORT: String(sdkPort),
        DOCUMENT_EDITOR_PLUGIN_ROOT: pluginRoot,
      },
      stdio: ["ignore", "ignore", "ignore"],
    });
    child.on("exit", () => resolve());
    child.on("error", () => resolve());
    setTimeout(() => resolve(), 12000);
  });
  if (await portOpen(sdkPort)) return true;
  vscode.window.showErrorMessage(
    "Document Present: editor_sdk 未就绪。请设置 EDITOR_SDK_BIN 或运行 bash scripts/fetch-sdk.sh"
  );
  return false;
}

function buildOfficeEmbedHtml(sdkUrl) {
  const csp = [
    "default-src 'none'",
    "frame-src http://127.0.0.1:* http://localhost:*",
    "style-src 'unsafe-inline'",
    "script-src 'unsafe-inline'",
  ].join("; ");
  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta http-equiv="Content-Security-Policy" content="${csp}"/>
<style>
  html,body{margin:0;height:100%;background:#f5f6f7}
  iframe{border:0;width:100%;height:100%;display:block}
  .bar{position:absolute;top:8px;right:12px;z-index:2;font:12px/1.4 -apple-system,sans-serif}
  .bar a{color:#1a6cff}
</style>
</head>
<body>
  <div class="bar"><a href="${sdkUrl}" id="ext">在浏览器打开</a></div>
  <iframe src="${sdkUrl}" title="Tencent editor_sdk" allow="clipboard-read; clipboard-write"></iframe>
  <script>
    const vscode = acquireVsCodeApi();
    document.getElementById('ext').addEventListener('click', (e) => {
      e.preventDefault();
      vscode.postMessage({ type: 'openExternal', url: ${JSON.stringify(sdkUrl)} });
    });
  </script>
</body>
</html>`;
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
    const pluginRoot = getPluginRoot(this.context);
    webviewPanel.webview.options = {
      enableScripts: true,
      // Allow iframe to editor_sdk on 127.0.0.1
      localResourceRoots: [],
    };

    // Office / PDF → embed Tencent editor_sdk visual UI
    if (isOfficePath(fsPath)) {
      const sdkPort = getSdkPort();
      const sdkOk = await ensureSdk(pluginRoot, sdkPort);
      const sdkUrl = buildSdkPreviewUrl(fsPath, sdkPort);
      if (sdkOk && sdkUrl) {
        webviewPanel.webview.html = buildOfficeEmbedHtml(sdkUrl);
      } else {
        webviewPanel.webview.html = `<!DOCTYPE html><html><body style="font:13px/1.5 -apple-system,sans-serif;padding:16px">
          <p>editor_sdk 未就绪，无法打开 Office 可视化编辑。</p>
          <p>请运行 <code>bash scripts/fetch-sdk.sh</code> 与 <code>bash scripts/install-local.sh</code>，然后 Reload Window。</p>
        </body></html>`;
      }
      webviewPanel.webview.onDidReceiveMessage(async (msg) => {
        if (!msg || !msg.type) return;
        if (msg.type === "openExternal" && msg.url) {
          await vscode.env.openExternal(vscode.Uri.parse(String(msg.url)));
        }
      });
      return;
    }

    const port = getPort();
    const ok = await ensureDaemon(pluginRoot, port);
    const url = presentUrl(fsPath, port);

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
    "*.docx": VIEW_TYPE,
    "*.xlsx": VIEW_TYPE,
    "*.pptx": VIEW_TYPE,
    "*.pdf": VIEW_TYPE,
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
