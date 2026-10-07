/*! Guest bootstrap for local editor_sdk (Cursor iframe).
 * Exposes window.mqq for optional native bridge; SDK native AI is OFF
 * (__WB_DOCS_FEATURE_LIST__.aiEdit=false). Hermes AI is float_toolbar_ai.js.
 */
(function () {
  if (window.__hermesMqqInjected) return;
  window.__hermesMqqInjected = true;

  // Disable SDK native float AI (AiEdit / WorkBuddy guest button)
  try {
    window.__WB_DOCS_FEATURE_LIST__ = { aiEdit: false };
  } catch (_) {
    /* ignore */
  }

  // Hide any leftover SDK AI entrances; keep Hermes [data-hermes-ai-btn]
  try {
    var st = document.createElement("style");
    st.setAttribute("data-hermes-hide-sdk-ai", "1");
    st.textContent =
      '[class*="float-toolbar"] [class*="ai-edit"],' +
      '[class*="float-toolbar"] [class*="AiEdit"],' +
      '[class*="float-toolbar"] [data-key="aiEdit"],' +
      '[class*="float-toolbar"] [data-menu-id="aiEdit"],' +
      '[class*="float-toolbar"] [id*="aiEdit"],' +
      '[class*="float-toolbar"] [class*="aiAsk"],' +
      '[class*="float-toolbar"] [data-key="aiAsk"]' +
      "{display:none!important}";
    (document.head || document.documentElement).appendChild(st);
  } catch (_) {
    /* ignore */
  }

  function apiName(moduleName, methodName) {
    return String(moduleName || "") + "." + String(methodName || "");
  }

  function okResult(data) {
    return { code: 0, data: data, hasHandled: true };
  }

  function post(type, payload, sendAction) {
    var msg = {
      source: "hermes-tencent-doc-mqq",
      type: type,
      sendAction: !!sendAction,
      payload: payload || null,
      href: String(location.href || ""),
      ts: Date.now(),
    };
    try {
      if (type === "selectionChange" || type === "selectionSend") {
        document.dispatchEvent(
          new CustomEvent("hermes-mqq-selection", { detail: payload || null })
        );
      }
    } catch (_) {
      /* ignore */
    }
    try {
      window.parent && window.parent.postMessage(msg, "*");
    } catch (_) {
      /* ignore */
    }
    try {
      window.top && window.top !== window && window.top.postMessage(msg, "*");
    } catch (_) {
      /* ignore */
    }
  }

  function handleInvoke(moduleName, methodName, args, callback) {
    var name = apiName(moduleName, methodName);
    var raw = args;
    if (Array.isArray(raw) && raw.length === 1) raw = raw[0];
    var payload = raw && typeof raw === "object" ? raw : {};
    if (name === "docx.onSelectionChange") {
      post("selectionChange", payload, false);
      callback && callback(okResult({ ok: true }));
      return;
    }
    if (name === "docx.onSelectionSend") {
      post("selectionSend", payload, true);
      callback && callback(okResult({ ok: true }));
      return;
    }
    if (name === "docx.onDocumentStatusChanged") {
      post("documentStatus", payload, false);
      callback && callback(okResult({ ok: true }));
      return;
    }
    if (name === "workbuddy.reportTelemetry") {
      callback && callback(okResult({ ok: true }));
      return;
    }
    if (String(name).indexOf("subscriber.") === 0) {
      callback && callback(okResult({ ok: true }));
      return;
    }
    callback &&
      callback({
        code: -32601,
        err: "mqq API is not implemented",
        hasHandled: false,
      });
  }

  var mqq = {
    invoke: function (moduleName, methodName, args, callback) {
      try {
        handleInvoke(moduleName, methodName, args || {}, callback);
      } catch (e) {
        callback &&
          callback({
            code: -32603,
            err: e && e.message ? e.message : String(e),
            hasHandled: false,
          });
      }
    },
    addEventListener: function () {
      return true;
    },
    removeEventListener: function () {},
    execEventCallback: function () {
      return Promise.resolve(undefined);
    },
    createSubscribe: function () {
      return {
        subscribe: function () {
          return 1;
        },
        unsubscribe: function () {},
      };
    },
  };

  try {
    Object.defineProperty(window, "mqq", {
      configurable: true,
      enumerable: true,
      get: function () {
        return mqq;
      },
      set: function () {
        /* keep shim */
      },
    });
  } catch (_) {
    window.mqq = mqq;
  }

  post("mqqReady", { ok: true }, false);
})();
