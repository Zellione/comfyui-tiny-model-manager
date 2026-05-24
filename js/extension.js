import { app } from "../../scripts/app.js";

const API = "/tiny-model-manager/api";
let _initialized = false;

async function fetchSettings() {
  const r = await fetch(`${API}/settings`);
  const j = await r.json();
  return j.success ? j.data : {};
}

async function putSetting(key, value) {
  await fetch(`${API}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ [key]: value }),
  });
}

app.registerExtension({
  name: "TinyModelManager.Settings",
  async setup() {
    const data = await fetchSettings();
    app.ui.settings.setSettingValue("TinyModelManager.civitai_api_key", data.civitai_api_key ?? "");
    app.ui.settings.setSettingValue("TinyModelManager.hf_token",        data.hf_token        ?? "");
    app.ui.settings.setSettingValue("TinyModelManager.media_dir",       data.media_dir        ?? "");
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
      type: "text",
      defaultVal: "",
      tooltip: "Absolute path for preview image storage. Leave blank to use the default (data/media/).",
      async onChange(value) {
        if (!_initialized) return;
        await putSetting("media_dir", value ?? "");
      },
    },
  ],
});
