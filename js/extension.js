import { app } from "../../scripts/app.js";
import { createPendingProcessor } from "./workflow-insert.js";

const API = "/tiny-model-manager/api";
let _initialized = false;
let _defaultMediaDir = "";
let _revertingOrganize = false;

async function fetchSettings() {
  const r = await fetch(`${API}/settings`);
  const j = await r.json();
  return j.success ? j.data : {};
}

async function putSetting(key, value) {
  const r = await fetch(`${API}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ [key]: value }),
  });
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    return { ok: false, error: j.error ?? "Unknown error" };
  }
  return { ok: true };
}

function makeToggle(checked, setter) {
  const label = document.createElement("label");
  label.style.cssText =
    "position:relative;display:inline-block;width:40px;height:22px;cursor:pointer;vertical-align:middle";

  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = !!checked;
  input.style.cssText = "opacity:0;width:0;height:0;position:absolute";

  const track = document.createElement("span");
  track.style.cssText =
    "position:absolute;inset:0;border-radius:11px;transition:background .2s";

  const thumb = document.createElement("span");
  thumb.style.cssText =
    "position:absolute;top:3px;width:16px;height:16px;border-radius:50%;background:#fff;transition:left .2s";
  track.appendChild(thumb);

  const refresh = (val) => {
    track.style.background = val ? "#00aa7e" : "#555";
    thumb.style.left = val ? "21px" : "3px";
  };
  refresh(input.checked);

  input.addEventListener("change", () => {
    refresh(input.checked);
    setter(input.checked);
  });

  label.append(input, track);
  return label;
}

app.registerExtension({
  name: "TinyModelManager.Settings",
  async setup() {
    const data = await fetchSettings();
    _defaultMediaDir = data.media_dir_default ?? "";
    app.ui.settings.setSettingValue("TinyModelManager.civitai_api_key",          data.civitai_api_key          ?? "");
    app.ui.settings.setSettingValue("TinyModelManager.hf_token",                 data.hf_token                 ?? "");
    app.ui.settings.setSettingValue("TinyModelManager.media_dir",                data.media_dir                ?? "");
    app.ui.settings.setSettingValue("TinyModelManager.organize_into_subfolders", data.organize_into_subfolders ?? false);
    _initialized = true;
  },
  settings: [
    {
      id: "TinyModelManager.civitai_api_key",
      name: "CivitAI API Key",
      category: ["Tiny Model Manager", "Credentials", "CivitAI API Key"],
      type: "text",
      defaultVal: "",
      tooltip: "Bearer token for private/gated models on CivitAI. Leave blank if unused.",
      async onChange(value) {
        if (!_initialized || !value || value === "***") return;
        await putSetting("civitai_api_key", value);
      },
    },
    {
      id: "TinyModelManager.hf_token",
      name: "HuggingFace Token",
      category: ["Tiny Model Manager", "Credentials", "HuggingFace Token"],
      type: "text",
      defaultVal: "",
      tooltip: "Access token for gated models on HuggingFace. Leave blank if unused.",
      async onChange(value) {
        if (!_initialized || !value || value === "***") return;
        await putSetting("hf_token", value);
      },
    },
    {
      id: "TinyModelManager.media_dir",
      name: "Media Storage Directory",
      category: ["Tiny Model Manager", "Storage", "Media Storage Directory"],
      type(_name, setter, value) {
        const row = document.createElement("div");
        row.style.cssText = "display:flex;gap:6px;align-items:center;width:100%";

        const input = document.createElement("input");
        input.type = "text";
        input.value = value || "";
        input.placeholder = _defaultMediaDir;
        input.style.cssText =
          "flex:1;min-width:0;padding:4px 6px;border-radius:4px;" +
          "background:var(--comfy-input-bg,#1a1a2e);border:1px solid var(--border-color,#444);color:inherit";
        input.addEventListener("change", () => setter(input.value));

        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = "Restore default";
        btn.style.cssText =
          "padding:4px 8px;border-radius:4px;cursor:pointer;white-space:nowrap;" +
          "background:var(--comfy-input-bg,#1a1a2e);border:1px solid var(--border-color,#444);color:inherit";
        btn.addEventListener("click", () => {
          input.value = "";
          setter("");
        });

        row.append(input, btn);
        return row;
      },
      defaultVal: "",
      tooltip: "Absolute path for preview image storage. Leave blank to use the default.",
      async onChange(value) {
        if (!_initialized) return;
        await putSetting("media_dir", value ?? "");
      },
    },
    {
      id: "TinyModelManager.organize_into_subfolders",
      name: "Organize models into subfolders",
      category: ["Tiny Model Manager", "Storage", "Organize into subfolders"],
      type(_name, setter, value) {
        return makeToggle(value, (checked) => {
          setter(checked);
        });
      },
      defaultVal: false,
      tooltip: "When enabled, newly downloaded models are placed in <type>/<base-model>/<filename> automatically.",
      async onChange(value) {
        if (!_initialized) return;
        if (_revertingOrganize) return;

        const msg = value
          ? "Enabling this will move all existing flat models into base-model subfolders.\nContinue?"
          : "Disabling this will move all models from subfolders back to flat type directories.\nContinue?";

        if (!confirm(msg)) {
          _revertingOrganize = true;
          app.ui.settings.setSettingValue("TinyModelManager.organize_into_subfolders", !value);
          _revertingOrganize = false;
          return;
        }

        const result = await putSetting("organize_into_subfolders", value);
        if (result.ok) {
          const ch = new BroadcastChannel("tmm");
          ch.postMessage({ key: "organize_into_subfolders", value });
          ch.close();
        } else {
          alert(`Could not change setting:\n${result.error}`);
          _revertingOrganize = true;
          const data = await fetchSettings();
          app.ui.settings.setSettingValue(
            "TinyModelManager.organize_into_subfolders",
            data.organize_into_subfolders ?? false,
          );
          _revertingOrganize = false;
        }
      },
    },
  ],
});

app.registerExtension({
  name: "TinyModelManager.WorkflowInsert",
  async setup() {
    const processPending = createPendingProcessor({
      app,
      liteGraph: LiteGraph,
      api: API,
    });
    setInterval(processPending, 500);
  },
});

app.registerExtension({
  name: "TinyModelManager.DashboardButton",
  async setup() {
    const insert = () => {
      if (document.getElementById("tmm-dashboard-btn")) return true;

      // ComfyUI ≥0.22 (Vue frontend): the legacy-topbar-container is hidden by
      // a Tailwind `:has(*>*:not(:empty))` guard that only shows it when it holds
      // element grandchildren — a plain text button never triggers it.
      // Insert into its parent (the always-visible action-bar row) instead.
      // Older ComfyUI (LiteGraph menu): fall back to .comfyui-menu-right / .comfyui-menu.
      const legacy = document.querySelector('[data-testid="legacy-topbar-container"]');
      const target =
        legacy?.parentElement ??
        document.querySelector(".comfyui-menu-right") ??
        document.querySelector(".comfyui-menu");
      if (!target) return false;

      const btn = document.createElement("button");
      btn.id = "tmm-dashboard-btn";
      btn.className = "comfyui-button";
      btn.title = "Open Tiny Model Manager";
      btn.textContent = "TMM";
      btn.style.cssText =
        "padding:4px 10px;font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap";
      btn.addEventListener("click", () => window.open("/tiny-model-manager", "_blank"));

      // Place just before the legacy slot so we don't displace the queue button.
      legacy ? legacy.before(btn) : target.prepend(btn);
      return true;
    };

    // setup() runs before Vue mounts, so the topbar element may not exist yet.
    if (!insert()) {
      const observer = new MutationObserver(() => {
        if (insert()) observer.disconnect();
      });
      observer.observe(document.body, { childList: true, subtree: true });
    }
  },
});
