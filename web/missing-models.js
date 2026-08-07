// Route ComfyUI's "Missing Models" panel through Tiny Model Manager (F-144).
//
// Kept free of ComfyUI imports and module-level side effects so it can be unit tested
// outside ComfyUI; `extension.js` injects the real `app`.
//
// Why buttons and not an interception: ComfyUI's own `downloadModel()` lives in a lazily
// loaded ESM chunk and its Pinia store is exposed on neither `window` nor `app`, so there is
// no hook to reuse. Outside the Electron desktop build the native button does not even reach
// the models folder — it clicks an `<a download>` and the file lands in the browser's
// Downloads directory. Our button sits next to it and leaves it untouched.

// Anchors from ComfyUI's MissingModelCard.vue / MissingModelRow.vue. `copy-name` is the only
// per-row control rendered unconditionally, which makes it the reliable row anchor.
const ROW_ANCHOR = '[data-testid="missing-model-copy-name"]';
const ACTIONS_ANCHOR = '[data-testid="missing-model-actions"]';

// Marker attributes keep sync() idempotent: Vue re-creates rows on every store change, and a
// fresh row simply has no marker yet.
const ROW_MARK = 'data-tmm-missing';
const ACTIONS_MARK = 'data-tmm-missing-all';

const POLL_MS = 500;
// A category heading reads "<directory> (<count>)". Only the bounded, anchored counter is
// matched and the name is recovered by stripping it — capturing the prefix with `(.*?)\s*`
// instead makes the engine retry at every position and costs O(n²) on a long heading
// (sonar javascript:S8786). Same shape as INDEX_SUFFIX in workflow-insert.js.
const GROUP_COUNT_SUFFIX = /\(\d{1,6}\)$/;
const FOLDER_NAME = /^\w{1,64}$/;

const BUTTON_CSS =
  'height:2rem;padding:0 .625rem;border-radius:.5rem;font-size:.8125rem;font-weight:500;' +
  'white-space:nowrap;cursor:pointer;background:var(--comfy-input-bg,#1a1a2e);' +
  'border:1px solid var(--border-color,#444);color:inherit';

export const LABELS = {
  idle: 'TMM',
  queued: 'TMM …',
  done: 'TMM ✓',
  failed: 'TMM ✗',
  installed: 'Installed',
  search: 'Search in TMM',
  all: 'Download all with TMM',
};

export function taskKey(directory, filename) {
  return `${directory}::${filename}`;
}

/** Strip the " (N)" count ComfyUI appends to a category heading. */
export function parseGroupDirectory(text) {
  const trimmed = (text ?? '').trim();
  if (!GROUP_COUNT_SUFFIX.test(trimmed)) return '';
  const name = trimmed.replace(GROUP_COUNT_SUFFIX, '').trim();
  return FOLDER_NAME.test(name) ? name : '';
}

// Collect every `{name, url, directory}` the workflow knows about, from both places ComfyUI's
// own missingModelScan.ts looks:
//
//  1. `node.properties.models` — survives on the live graph, so it is read straight off it.
//  2. The workflow's TOP-LEVEL `models` array. This one is not on the graph at all:
//     `LGraph.configure()` does `this.extra = data.extra`, and `models` is a sibling of
//     `extra`, so it is dropped. Reading `graph.extra.models` finds nothing — ever. ComfyUI
//     runs the array through its missing-model pipeline and caches the result on the active
//     workflow, and that cache is the only copy an extension can reach.
//
// Missing (2) is what made an LTX workflow report "unresolved" while carrying a usable
// HuggingFace URL: the URL simply never reached the backend.
export function buildModelIndex(app) {
  const index = new Map();
  const add = (entry) => {
    const name = entry?.name;
    if (!name) return;
    if (!index.has(name)) index.set(name, []);
    index.get(name).push({ url: entry.url ?? '', directory: entry.directory ?? '' });
  };

  const graph = app?.rootGraph ?? app?.graph;
  for (const node of graph?.nodes ?? []) {
    for (const model of node?.properties?.models ?? []) add(model);
  }
  // `app.extensionManager` is ComfyUI's workspace store; `.workflow` is the workflow store.
  // Candidates carry `{name, url, directory}` — the same fields the panel renders from.
  const warnings = app?.extensionManager?.workflow?.activeWorkflow?.pendingWarnings;
  for (const candidate of warnings?.missingModelCandidates ?? []) add(candidate);
  return index;
}

/** Pick the indexed entry for a filename, preferring one whose directory agrees. */
export function lookupModel(index, filename, directory) {
  const entries = index.get(filename) ?? [];
  return entries.find((e) => e.directory === directory) ?? entries[0] ?? null;
}

// Read one panel row: its filename, its directory and the header element to append to.
// Returns null when the row's directory cannot be established — those rows get no button,
// because guessing a folder is how a LoRA ends up in checkpoints.
export function readRow(copyButton, index) {
  const header = copyButton.parentElement?.parentElement;
  const nameNode = copyButton.parentElement?.querySelector('p[title]');
  const filename = nameNode?.getAttribute('title')?.trim() ?? '';
  if (!header || !filename) return null;

  // group → rows container → row root → header
  const group = header.parentElement?.parentElement?.parentElement;
  const fromHeading = parseGroupDirectory(group?.querySelector('p')?.textContent);
  const indexed = lookupModel(index, filename, fromHeading);
  const directory = fromHeading || indexed?.directory || '';
  if (!FOLDER_NAME.test(directory)) return null;

  return { header, filename, directory, url: indexed?.url ?? '' };
}

// Render one button from its entry. Closes over nothing but LABELS, so it lives at module
// scope: a per-integration copy would be rebuilt for no reason (sonar javascript:S7721).
function paint(button, entry) {
  button.textContent = LABELS[entry.state] ?? LABELS.idle;
  if (entry.state === 'queued' && entry.progress > 0) {
    button.textContent = `TMM ${Math.round(entry.progress)}%`;
  }
  button.title = entry.error || `Download ${entry.filename} through Tiny Model Manager`;
  button.disabled = entry.state === 'queued' || entry.state === 'installed';
  button.style.opacity = button.disabled ? '0.6' : '1';
}

export function createMissingModelsIntegration({
  app,
  api,
  fetchFn = fetch,
  doc = document,
  openWindow = (url) => window.open(url, '_blank'),
}) {
  // Keyed by directory::filename so a button re-injected into a re-rendered row picks its
  // state back up instead of falling back to "idle".
  const entries = new Map();
  // `buttons` is keyed for repainting; `injected` holds every button we created — including
  // "Download all", which has no key — so stop() can remove all of them.
  const buttons = new Map();
  const injected = new Set();
  let observer = null;
  let pollTimer = null;
  let polling = false;
  let syncing = false;

  const toast = (severity, summary, detail) => {
    try {
      app?.extensionManager?.toast?.add?.({ severity, summary, detail, life: 5000 });
    } catch {
      // A missing toast manager must never break a download.
    }
  };

  const refreshComfyModels = async () => {
    try {
      if (typeof app?.refreshComboInNodes === 'function') await app.refreshComboInNodes();
    } catch {
      // ignored — the model list just stays stale until the next refresh
    }
  };

  function setState(key, patch) {
    const entry = { ...entries.get(key), ...patch };
    entries.set(key, entry);
    const button = buttons.get(key);
    if (button) paint(button, entry);
    return entry;
  }

  function openDashboardSearch(entry) {
    const params = new URLSearchParams({
      q: entry.searchTerm,
      platform: 'civitai',
      type: entry.directory,
    });
    openWindow(`/tiny-model-manager/download?${params}`);
  }

  async function requestDownload(row) {
    const key = taskKey(row.directory, row.filename);
    const entry = entries.get(key);
    if (entry?.state === 'queued' || entry?.state === 'installed') return;
    if (entry?.state === 'search') {
      openDashboardSearch(entry);
      return;
    }

    // Only the plain fields — never `row.header`, which Vue replaces on every re-render.
    setState(key, {
      filename: row.filename,
      directory: row.directory,
      state: 'queued',
      progress: 0,
      error: '',
    });
    let payload;
    try {
      const response = await fetchFn(`${api}/download/missing`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: row.filename,
          directory: row.directory,
          url: row.url,
        }),
      });
      payload = await response.json();
    } catch (error) {
      payload = { success: false, error: String(error) };
    }

    if (!payload?.success) {
      setState(key, { state: 'failed', error: payload?.error ?? 'Request failed' });
      toast(
        'error',
        'Tiny Model Manager',
        `${row.filename}: ${payload?.error ?? 'Request failed'}`,
      );
      return;
    }

    const data = payload.data ?? {};
    if (data.already_installed) {
      setState(key, { state: 'installed' });
      toast('info', 'Tiny Model Manager', `${row.filename} is already installed.`);
      return;
    }
    if (data.unresolved) {
      setState(key, { state: 'search', searchTerm: data.search_term });
      toast(
        'warn',
        'Tiny Model Manager',
        `No exact match for ${row.filename}. Use "Search in TMM" to look for it yourself.`,
      );
      return;
    }
    setState(key, { state: 'queued', taskId: data.task_id });
    toast('info', 'Tiny Model Manager', `Queued ${row.filename}.`);
    startPolling();
  }

  function applyTaskStatuses(tasks) {
    const byId = new Map(tasks.map((task) => [task.id, task]));
    let active = 0;
    for (const [key, entry] of entries) {
      if (entry.state !== 'queued' || !entry.taskId) continue;
      const task = byId.get(entry.taskId);
      // A task the backend has already forgotten (its 60 s grace window elapsed while this
      // tab was hidden) counts as finished, not as stuck.
      if (!task) {
        setState(key, { state: 'done' });
        continue;
      }
      if (task.status === 'done') {
        setState(key, { state: 'done', progress: 100 });
        toast('success', 'Tiny Model Manager', `${entry.filename} downloaded.`);
        void refreshComfyModels();
      } else if (task.status === 'error' || task.status === 'cancelled') {
        setState(key, { state: 'failed', error: task.error ?? task.status });
        toast('error', 'Tiny Model Manager', `${entry.filename}: ${task.error ?? task.status}`);
      } else {
        setState(key, { progress: task.progress ?? 0 });
        active += 1;
      }
    }
    return active;
  }

  async function pollOnce() {
    if (polling) return;
    polling = true;
    try {
      const response = await fetchFn(`${api}/download/status`);
      const payload = await response.json();
      if (!payload?.success) return;
      if (applyTaskStatuses(payload.data ?? []) === 0) stopPolling();
    } catch {
      // Keep the timer running: a transient failure must not freeze every button.
    } finally {
      polling = false;
    }
  }

  function startPolling() {
    if (pollTimer === null) pollTimer = setInterval(pollOnce, POLL_MS);
  }

  function stopPolling() {
    if (pollTimer !== null) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function makeButton(label, onClick) {
    const button = doc.createElement('button');
    button.type = 'button';
    button.className = 'tmm-missing-btn';
    button.textContent = label;
    button.style.cssText = BUTTON_CSS;
    button.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      void onClick();
    });
    injected.add(button);
    return button;
  }

  function injectRows(index) {
    const rows = [];
    for (const copyButton of doc.querySelectorAll(ROW_ANCHOR)) {
      const row = readRow(copyButton, index);
      if (!row) continue;
      rows.push(row);
      if (row.header.hasAttribute(ROW_MARK)) continue;
      row.header.setAttribute(ROW_MARK, '');

      const key = taskKey(row.directory, row.filename);
      const button = makeButton(LABELS.idle, () => requestDownload(row));
      buttons.set(key, button);
      paint(button, entries.get(key) ?? { filename: row.filename, state: 'idle' });
      row.header.appendChild(button);
    }
    return rows;
  }

  function injectDownloadAll(getRows) {
    const actions = doc.querySelector(ACTIONS_ANCHOR);
    if (!actions || actions.hasAttribute(ACTIONS_MARK)) return;
    actions.setAttribute(ACTIONS_MARK, '');
    actions.appendChild(
      makeButton(LABELS.all, async () => {
        // Sequential on purpose: each request may run a provider search, and a panel with a
        // dozen entries would otherwise fire a dozen searches at once. The download queue
        // serialises the transfers itself.
        for (const row of getRows()) {
          await requestDownload(row);
        }
      }),
    );
  }

  function sync() {
    // Our own appendChild calls are mutations too — without this guard the observer would
    // re-enter sync() forever.
    if (syncing) return;
    syncing = true;
    try {
      const index = buildModelIndex(app);
      const rows = injectRows(index);
      injectDownloadAll(() => rows);
    } finally {
      syncing = false;
    }
  }

  function start() {
    if (observer) return;
    observer = new MutationObserver(() => sync());
    observer.observe(doc.body, { childList: true, subtree: true });
    sync();
  }

  function stop() {
    observer?.disconnect();
    observer = null;
    stopPolling();
    for (const button of injected) button.remove();
    injected.clear();
    buttons.clear();
    for (const marked of doc.querySelectorAll(`[${ROW_MARK}],[${ACTIONS_MARK}]`)) {
      marked.removeAttribute(ROW_MARK);
      marked.removeAttribute(ACTIONS_MARK);
    }
  }

  return { start, stop, sync };
}
