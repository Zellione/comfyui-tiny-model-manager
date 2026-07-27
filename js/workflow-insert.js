// Workflow-insert logic for the ComfyUI extension.
//
// Kept free of ComfyUI imports and module-level side effects so it can be unit
// tested outside ComfyUI; `extension.js` injects the real `app` / `LiteGraph`.

export const NODE_TYPE_MAP = {
  checkpoints:    { node: "TMMCheckpointLoader",    widget: "ckpt_name" },
  loras:          { node: "TMMLoraLoader",          widget: "lora_name" },
  vae:            { node: "TMMVaeLoader",           widget: "vae_name" },
  controlnet:     { node: "TMMControlNetLoader",    widget: "control_net_name" },
  embeddings:     { node: "TMMEmbeddingHelper",     widget: "embedding_name" },
  upscale_models: { node: "TMMUpscaleModelLoader",  widget: "model_name" },
};

// Strip ComfyUI's " (N)" disambiguation suffix from a filename's stem.
export function stripSuffix(s) {
  const slash = Math.max(s.lastIndexOf('/'), s.lastIndexOf('\\'));
  const dir   = slash >= 0 ? s.slice(0, slash + 1) : '';
  const base  = slash >= 0 ? s.slice(slash + 1) : s;
  const dot   = base.lastIndexOf('.');
  const stem  = dot >= 0 ? base.slice(0, dot) : base;
  const ext   = dot >= 0 ? base.slice(dot) : '';
  return dir + stem.replace(/\s*\(\d+\)$/, '') + ext;
}

// Resolve the best matching option in a COMBO widget for a given filename.
// ComfyUI appends " (N)" to disambiguate files with the same relative path
// across multiple model directories. This function handles that mismatch.
export function findWidgetOption(widget, filename) {
  const options = widget.options?.values ?? [];
  if (options.includes(filename)) return filename;

  const cleanFile = stripSuffix(filename);
  return (
    options.find(o => stripSuffix(o) === filename)  // option has suffix, we don't
    ?? options.find(o => o === cleanFile)            // we have suffix, option doesn't
    ?? filename                                       // fallback
  );
}

// Ask ComfyUI to re-read its model folders so files downloaded after the tab
// was loaded appear in loader COMBO widgets without a page reload.
// Best-effort: older frontends may not expose it, and a failed refresh must
// never stop us from inserting the node.
export async function refreshComfyModels(app) {
  try {
    if (typeof app?.refreshComboInNodes === "function") {
      await app.refreshComboInNodes();
    }
  } catch {
    // ignored — insertion proceeds with the stale option list
  }
}

// Build the poll tick that drains the backend's pending-insert queue.
export function createPendingProcessor({ app, liteGraph, api, fetchFn = fetch }) {
  // Pending items are only dropped once acked, and the model refresh can take
  // longer than the poll interval — without this guard an overlapping tick
  // would insert the same node twice.
  let running = false;

  return async function processPending() {
    if (running) return;
    running = true;
    try {
      let j;
      try {
        const r = await fetchFn(`${api}/workflow/pending`);
        j = await r.json();
      } catch {
        return;
      }
      if (!j.success || !j.data.length) return;

      // Once per batch, before any node is created.
      await refreshComfyModels(app);

      for (const item of j.data) {
        const mapping = NODE_TYPE_MAP[item.model_type];
        if (!mapping) continue;
        const node = liteGraph.createNode(mapping.node);
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
        await fetchFn(`${api}/workflow/ack`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: item.id }),
        });
      }
    } finally {
      running = false;
    }
  };
}
