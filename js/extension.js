import { app } from "../../scripts/app.js";

const API = "/tiny-model-manager/api";
let _initialized = false;
let _defaultMediaDir = "";

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
        const result = await putSetting("organize_into_subfolders", value);
        if (!result.ok) {
          alert(`Could not change setting:\n${result.error}`);
          // Revert by re-applying the saved value from the backend
          const data = await fetchSettings();
          app.ui.settings.setSettingValue(
            "TinyModelManager.organize_into_subfolders",
            data.organize_into_subfolders ?? false,
          );
        }
      },
    },
  ],
});

const NODE_TYPE_MAP = {
  checkpoints:    { node: "TMMCheckpointLoader",    widget: "ckpt_name" },
  loras:          { node: "TMMLoraLoader",          widget: "lora_name" },
  vae:            { node: "TMMVaeLoader",           widget: "vae_name" },
  controlnet:     { node: "TMMControlNetLoader",    widget: "control_net_name" },
  embeddings:     { node: "TMMEmbeddingHelper",     widget: "embedding_name" },
  upscale_models: { node: "TMMUpscaleModelLoader",  widget: "model_name" },
};

// Resolve the best matching option in a COMBO widget for a given filename.
// ComfyUI appends " (N)" to disambiguate files with the same relative path
// across multiple model directories. This function handles that mismatch.
function findWidgetOption(widget, filename) {
  const options = widget.options?.values ?? [];
  if (options.includes(filename)) return filename;

  function stripSuffix(s) {
    const slash = Math.max(s.lastIndexOf('/'), s.lastIndexOf('\\'));
    const dir   = slash >= 0 ? s.slice(0, slash + 1) : '';
    const base  = slash >= 0 ? s.slice(slash + 1) : s;
    const dot   = base.lastIndexOf('.');
    const stem  = dot >= 0 ? base.slice(0, dot) : base;
    const ext   = dot >= 0 ? base.slice(dot) : '';
    return dir + stem.replace(/\s*\(\d+\)$/, '') + ext;
  }

  const cleanFile = stripSuffix(filename);
  return (
    options.find(o => stripSuffix(o) === filename)  // option has suffix, we don't
    ?? options.find(o => o === cleanFile)            // we have suffix, option doesn't
    ?? filename                                       // fallback
  );
}

app.registerExtension({
  name: "TinyModelManager.WorkflowInsert",
  async setup() {
    setInterval(async () => {
      let j;
      try {
        const r = await fetch(`${API}/workflow/pending`);
        j = await r.json();
      } catch {
        return;
      }
      if (!j.success || !j.data.length) return;
      for (const item of j.data) {
        const mapping = NODE_TYPE_MAP[item.model_type];
        if (!mapping) continue;
        const node = LiteGraph.createNode(mapping.node);
        if (!node) continue;
        const widget = node.widgets?.find(w => w.name === mapping.widget);
        if (widget) widget.value = findWidgetOption(widget, item.filename);
        // Place at viewport centre so it's immediately visible
        const c = app.canvas;
        node.pos = [
          (c.canvas.width  / 2 - c.ds.offset[0]) / c.ds.scale,
          (c.canvas.height / 2 - c.ds.offset[1]) / c.ds.scale,
        ];
        app.graph.add(node);
        app.canvas.selectNode(node);
        app.graph.setDirtyCanvas(true, true);
        await fetch(`${API}/workflow/ack`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: item.id }),
        });
      }
    }, 500);
  },
});
