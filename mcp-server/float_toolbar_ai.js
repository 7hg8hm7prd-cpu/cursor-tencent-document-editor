/*! Hermes float-toolbar AI — WorkBuddy-like inline panel (not top bar).
 * Capture canvas selection via React fiber getPlainText; rewrite in-place UI.
 */
(function () {
  if (window.__hermesFloatToolbarAi) return;
  window.__hermesFloatToolbarAi = true;

  var lastSel = null;
  var panel = null;
  var pendingReplacement = "";

  function post(type, payload, extra) {
    var msg = Object.assign(
      {
        source: "hermes-tencent-doc-mqq",
        type: type,
        sendAction: true,
        via: "float",
        payload: payload || null,
        href: String(location.href || ""),
        ts: Date.now(),
      },
      extra || {}
    );
    try {
      window.parent && window.parent.postMessage(msg, "*");
    } catch (_) {}
    try {
      window.top && window.top !== window && window.top.postMessage(msg, "*");
    } catch (_) {}
  }

  function stashText(text, ranges, fileId, extra) {
    text = String(text || "").trim();
    if (!text && !(ranges && ranges.length)) return false;
    var payload = Object.assign(
      {
        description: text,
        selectedText: text,
        source: "doc",
        timestamp: Date.now(),
        ranges: ranges || null,
        fileId: fileId || "",
      },
      extra || {}
    );
    lastSel = {
      text: text,
      ranges: ranges || null,
      fileId: fileId || "",
      payload: payload,
    };
    return true;
  }

  document.addEventListener(
    "hermes-mqq-selection",
    function (ev) {
      if (!ev.detail || typeof ev.detail !== "object") return;
      var p = ev.detail;
      stashText(
        p.description || p.selectedText || p.text || "",
        Array.isArray(p.ranges) ? p.ranges : null,
        p.fileId || p.file_id || "",
        p
      );
    },
    false
  );

  function copySelectedText() {
    var text = "";
    function onCopy(ev) {
      try {
        text =
          (ev.clipboardData && ev.clipboardData.getData("text/plain")) || "";
      } catch (_) {}
      try {
        ev.preventDefault();
      } catch (_) {}
    }
    document.addEventListener("copy", onCopy, true);
    try {
      document.execCommand("copy");
    } catch (_) {}
    document.removeEventListener("copy", onCopy, true);
    return String(text || "").trim();
  }

  function tryGetPlainTextFromObj(obj, depth) {
    if (!obj || depth > 5) return "";
    try {
      if (typeof obj.getPlainText === "function") {
        var t = obj.getPlainText();
        if (t) return String(t);
      }
      if (obj.service && typeof obj.service.getSelection === "function") {
        var sel = obj.service.getSelection();
        if (sel && typeof sel.getPlainText === "function") {
          var t2 = sel.getPlainText();
          if (t2) return String(t2);
        }
      }
      if (obj.editor) {
        var t3 = tryGetPlainTextFromObj(obj.editor, depth + 1);
        if (t3) return t3;
      }
      if (obj.stateNode) {
        var t4 = tryGetPlainTextFromObj(obj.stateNode, depth + 1);
        if (t4) return t4;
      }
    } catch (_) {}
    return "";
  }

  function fiberPlainText(dom) {
    if (!dom) return "";
    var fiber = null;
    try {
      var keys = Object.keys(dom);
      for (var i = 0; i < keys.length; i++) {
        if (
          keys[i].indexOf("__reactFiber") === 0 ||
          keys[i].indexOf("__reactInternalInstance") === 0
        ) {
          fiber = dom[keys[i]];
          break;
        }
      }
    } catch (_) {
      return "";
    }
    for (var n = 0; n < 50 && fiber; n++, fiber = fiber.return) {
      var t = tryGetPlainTextFromObj(fiber.stateNode, 0);
      if (t) return t;
      t = tryGetPlainTextFromObj(fiber.memoizedProps, 0);
      if (t) return t;
      try {
        if (fiber.stateNode && fiber.stateNode.editor) {
          t = tryGetPlainTextFromObj(fiber.stateNode.editor, 0);
          if (t) return t;
        }
      } catch (_) {}
    }
    return "";
  }

  function captureNow(anchorDom) {
    var text = fiberPlainText(anchorDom);
    var method = text ? "fiber" : "";
    if (!text) {
      text = copySelectedText();
      if (text) method = "copy";
    }
    if (!text) {
      try {
        var s = window.getSelection && window.getSelection();
        if (s && String(s).trim()) {
          text = String(s).trim();
          method = "dom";
        }
      } catch (_) {}
    }
    if (!text && lastSel && lastSel.text) {
      text = lastSel.text;
      method = "stash";
    }
    if (text) stashText(text, lastSel && lastSel.ranges, lastSel && lastSel.fileId);
    return text || "";
  }

  function hidePanel() {
    if (panel && panel.parentNode) panel.parentNode.removeChild(panel);
    panel = null;
    pendingReplacement = "";
  }

  function setPanelStatus(text) {
    if (!panel) return;
    var st = panel.querySelector("[data-hermes-ai-status]");
    if (st) st.textContent = text || "";
  }

  function setPanelPreview(text) {
    if (!panel) return;
    var pre = panel.querySelector("[data-hermes-ai-preview]");
    var apply = panel.querySelector("[data-hermes-ai-apply]");
    if (pre) {
      pre.hidden = !text;
      pre.textContent = text || "";
    }
    if (apply) apply.disabled = !text;
  }

  function showPanel(anchor) {
    hidePanel();
    pendingReplacement = "";
    var text = (lastSel && lastSel.text) || "";
    panel = document.createElement("div");
    panel.setAttribute("data-hermes-ai-panel", "1");
    panel.style.cssText = [
      "position:absolute",
      "top:100%",
      "left:0",
      "margin-top:6px",
      "z-index:2147483646",
      "width:min(360px,70vw)",
      "padding:10px",
      "border-radius:8px",
      "background:#fff",
      "border:1px solid #d0d3d9",
      "box-shadow:0 8px 24px rgba(15,23,42,.16)",
      "font:12px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
      "color:#1f2329",
      "pointer-events:auto",
    ].join(";");
    panel.innerHTML =
      '<div style="font-weight:600;margin-bottom:6px">Hermes AI 改写</div>' +
      '<div style="color:#646a73;margin-bottom:6px;max-height:40px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" data-hermes-ai-sel></div>' +
      '<div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:6px">' +
      '<button type="button" data-q="润色这段文字，保持原意" style="padding:2px 8px;border-radius:999px;border:1px solid #d0d3d9;background:#fff;cursor:pointer">润色</button>' +
      '<button type="button" data-q="改短一点，更精练" style="padding:2px 8px;border-radius:999px;border:1px solid #d0d3d9;background:#fff;cursor:pointer">改短</button>' +
      '<button type="button" data-q="改成正式书面语气" style="padding:2px 8px;border-radius:999px;border:1px solid #d0d3d9;background:#fff;cursor:pointer">正式</button>' +
      '<button type="button" data-q="纠正语病与错别字，不改变原意" style="padding:2px 8px;border-radius:999px;border:1px solid #d0d3d9;background:#fff;cursor:pointer">纠错</button>' +
      "</div>" +
      '<textarea data-hermes-ai-inst placeholder="改写指令" style="width:100%;min-height:44px;box-sizing:border-box;border:1px solid #d0d3d9;border-radius:6px;padding:6px 8px;font:inherit;resize:vertical"></textarea>' +
      '<div style="display:flex;gap:6px;margin-top:6px;align-items:center">' +
      '<button type="button" data-hermes-ai-run style="padding:4px 10px;border:0;border-radius:6px;background:#1a6cff;color:#fff;font-weight:600;cursor:pointer">改写</button>' +
      '<button type="button" data-hermes-ai-apply disabled style="padding:4px 10px;border:1px solid #d0d3d9;border-radius:6px;background:#fff;cursor:pointer">写入选区</button>' +
      '<button type="button" data-hermes-ai-close style="padding:4px 10px;border:0;background:transparent;color:#646a73;cursor:pointer">关闭</button>' +
      "</div>" +
      '<div data-hermes-ai-status style="margin-top:6px;color:#646a73"></div>' +
      '<pre data-hermes-ai-preview hidden style="margin:6px 0 0;max-height:120px;overflow:auto;background:#f0f2f5;padding:8px;border-radius:6px;white-space:pre-wrap;word-break:break-word"></pre>';

    var host = anchor;
    if (host && host.style) {
      var pos = window.getComputedStyle(host).position;
      if (pos === "static") host.style.position = "relative";
    }
    (host || document.body).appendChild(panel);

    var selEl = panel.querySelector("[data-hermes-ai-sel]");
    if (selEl) selEl.textContent = text ? "选区：" + text.slice(0, 48) + (text.length > 48 ? "…" : "") : "未捕获选区";
    var inst = panel.querySelector("[data-hermes-ai-inst]");
    if (inst) inst.value = "润色这段文字，保持原意";

    panel.addEventListener("mousedown", function (e) {
      e.stopPropagation();
    });
    panel.addEventListener("click", function (e) {
      e.stopPropagation();
      var q = e.target && e.target.closest && e.target.closest("button[data-q]");
      if (q) {
        if (inst) inst.value = q.getAttribute("data-q") || "";
        runRewrite();
        return;
      }
      if (e.target && e.target.getAttribute("data-hermes-ai-run") != null) {
        runRewrite();
        return;
      }
      if (e.target && e.target.getAttribute("data-hermes-ai-apply") != null) {
        applyRewrite();
        return;
      }
      if (e.target && e.target.getAttribute("data-hermes-ai-close") != null) {
        hidePanel();
      }
    });
  }

  function currentPayload(aiPrompt) {
    var text = (lastSel && lastSel.text) || "";
    var payload =
      (lastSel && lastSel.payload && Object.assign({}, lastSel.payload)) || {
        source: "doc",
        timestamp: Date.now(),
      };
    if (text) {
      payload.description = text;
      payload.selectedText = text;
    }
    if (aiPrompt) payload.aiPrompt = String(aiPrompt);
    payload.via = "float";
    return payload;
  }

  function runRewrite() {
    var inst = panel && panel.querySelector("[data-hermes-ai-inst]");
    var prompt = (inst && inst.value ? inst.value : "").trim() || "润色这段文字，保持原意";
    var payload = currentPayload(prompt);
    if (!payload.description && !(payload.ranges && payload.ranges.length)) {
      setPanelStatus("选区为空，请重新划选");
      post("selectionSend", payload, { error: "empty_selection" });
      return;
    }
    setPanelStatus("正在改写…");
    setPanelPreview("");
    pendingReplacement = "";
    // Single message — parent runs Hermes, does not open top bar
    post("selectionSend", payload);
  }

  function applyRewrite() {
    if (!pendingReplacement) {
      setPanelStatus("请先改写");
      return;
    }
    setPanelStatus("正在写入…");
    post("floatAiApply", currentPayload(""), {
      replacement: pendingReplacement,
    });
  }

  window.addEventListener("message", function (ev) {
    var msg = ev.data;
    if (!msg || msg.source !== "hermes-tencent-doc-parent") return;
    if (msg.type === "officeAiResult") {
      if (msg.ok === false) {
        setPanelStatus(msg.error || "改写失败");
        return;
      }
      if (msg.applied) {
        setPanelStatus("已写入选区");
        setPanelPreview("");
        pendingReplacement = "";
        setTimeout(hidePanel, 800);
        return;
      }
      pendingReplacement = msg.replacement || "";
      setPanelPreview(pendingReplacement);
      setPanelStatus(pendingReplacement ? "预览就绪，可写入选区" : "无结果");
    }
  });

  function openFromToolbar(container) {
    captureNow(container);
    if (!(lastSel && lastSel.text)) {
    }
    showPanel(container);
  }

  function toolbarRow(container) {
    // Prefer the row that already holds format icons (same line as A+/B/I…).
    var kids = container.children || [];
    var i;
    var el;
    var cs;
    for (i = 0; i < kids.length; i++) {
      el = kids[i];
      if (!el || el.getAttribute && el.getAttribute("data-hermes-ai-btn")) continue;
      try {
        cs = window.getComputedStyle(el);
      } catch (_) {
        cs = null;
      }
      if (cs && (cs.display === "flex" || cs.display === "inline-flex")) {
        if (String(cs.flexDirection || "").indexOf("column") < 0) return el;
      }
      if (el.querySelector && el.querySelector("button,[role='button'],[class*='item']")) {
        return el;
      }
    }
    return container;
  }

  function ensureBtn(container) {
    if (!container || container.querySelector("[data-hermes-ai-btn]")) return;
    captureNow(container);
    var row = toolbarRow(container);
    var btn = document.createElement("button");
    btn.type = "button";
    btn.setAttribute("data-hermes-ai-btn", "1");
    btn.title = "AI 改写选区（Hermes）";
    btn.textContent = "AI";
    btn.style.cssText = [
      "display:inline-flex",
      "align-items:center",
      "justify-content:center",
      "margin-left:6px",
      "padding:0 8px",
      "height:24px",
      "min-width:28px",
      "border:0",
      "border-radius:4px",
      "background:#1a6cff",
      "color:#fff",
      "font:12px/1 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
      "font-weight:600",
      "cursor:pointer",
      "vertical-align:middle",
      "flex:0 0 auto",
      "align-self:center",
      "position:relative",
      "z-index:5",
      "white-space:nowrap",
    ].join(";");
    btn.addEventListener(
      "mousedown",
      function (e) {
        captureNow(container);
        e.preventDefault();
        e.stopPropagation();
      },
      true
    );
    btn.addEventListener(
      "click",
      function (e) {
        e.preventDefault();
        e.stopPropagation();
        openFromToolbar(container);
      },
      true
    );
    try {
      // Keep format icons + AI on one horizontal line.
      container.style.flexWrap = "nowrap";
      container.style.alignItems = "center";
      if (row && row !== container) {
        row.style.flexWrap = "nowrap";
        row.style.alignItems = "center";
        row.style.display = row.style.display || "flex";
      }
    } catch (_) {}
    row.appendChild(btn);
  }

  function scan(root) {
    var nodes = (root || document).querySelectorAll(
      '[class*="float-toolbar_container"]'
    );
    for (var i = 0; i < nodes.length; i++) ensureBtn(nodes[i]);
  }

  var obs = new MutationObserver(function () {
    scan(document);
  });
  function boot() {
    scan(document);
    try {
      obs.observe(document.documentElement, { childList: true, subtree: true });
    } catch (_) {}
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
