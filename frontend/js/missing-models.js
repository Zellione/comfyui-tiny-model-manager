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

// Anchors from ComfyUI's MissingModelCard.vue / MissingModelRow.vue.
//
// The panel is rewritten between frontend releases — 1.48 dropped every anchor 1.45 offered
// except `missing-model-actions` — so each anchor below is tried in turn rather than relied
// on alone. ComfyUI pins the frontend to an exact version, so an older install stays on an
// older DOM indefinitely and both paths have to keep working.
//
// 1.48 has no per-row testid at all: `expand`, `download`, `locate` and `reference-count` are
// each behind a `v-if`. The row containers are the only stable hold, and a row is one of their
// direct children.
const ROW_CONTAINERS = [
  '[data-testid="missing-model-importable-rows"]',
  '[data-testid="missing-model-import-not-supported-section"]',
];
// 1.45's per-row copy button. Removed in 1.48, which is what broke the integration.
const LEGACY_ROW_ANCHOR = '[data-testid="missing-model-copy-name"]';
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
// A directory scraped out of rendered UI text is held to a stricter shape than one read from
// workflow data, because the panel prints a LOCALIZED placeholder in the same slot when it
// does not know the folder: `modelTypeLabel = directory ?? t('…unknownCategory')`. Those
// translations are `Unknown`, `Desconocido`, `Inconnu`, `Bilinmeyen`, `Неизвестно`, … — every
// one either capitalised or non-ASCII, and `\w` would happily accept the Latin ones as a
// folder name. ComfyUI's own folders are all ASCII lowercase snake_case, so requiring that
// rejects the placeholder in every shipped locale.
const SCRAPED_FOLDER_NAME = /^[a-z][a-z0-9_]{0,63}$/;
// `modelMetadataLabel` joins the folder and the download size with this separator.
const METADATA_SEPARATOR = ' · ';

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

/** Strip the " (N)" count ComfyUI appends to a category heading (frontend <= 1.45). */
export function parseGroupDirectory(text) {
  const trimmed = (text ?? '').trim();
  if (!GROUP_COUNT_SUFFIX.test(trimmed)) return '';
  const name = trimmed.replace(GROUP_COUNT_SUFFIX, '').trim();
  return SCRAPED_FOLDER_NAME.test(name) ? name : '';
}

/**
 * Read the folder out of a row's own metadata line, "checkpoints · 6.86 GB" (frontend >= 1.48,
 * which dropped the per-directory groups and prints the folder inside each row instead).
 */
export function parseMetadataDirectory(text) {
  const name = (text ?? '').split(METADATA_SEPARATOR)[0].trim();
  return SCRAPED_FOLDER_NAME.test(name) ? name : '';
}

// Every graph in the hierarchy, root first.
//
// Comfy-Org's templates put their loaders inside subgraphs, so a root-only walk finds none of the
// models they carry: the Wan 2.2 T2V template's root graph holds two notes, one subgraph instance
// and SaveVideo, while all six models sit in the subgraph. Two routes in, both live at once,
// because ComfyUI pins the frontend to an exact version and an older install stays on an older
// shape indefinitely — the same reason the panel-DOM reader tries each anchor in turn:
//   - `graph.subgraphs` when it is a Map: `LGraph.get subgraphs()` returns `rootGraph._subgraphs`,
//     the registry of every subgraph at any depth. ComfyUI's `findSubgraphByUuid` prefers it too.
//   - recursion through `node.isSubgraphNode() && node.subgraph`, which is what ComfyUI's own
//     `forEachNode` does, for whatever the registry does not carry.
//
// `seen` earns its keep twice: a subgraph that instantiates itself would otherwise hang the
// browser (ComfyUI's forEachNode has no guard, but `buildSubgraphExecutionPaths` does), and the
// two routes reach the same subgraph object, which `lookupModel` would not survive — it returns
// `entries[0]`, so a doubled entry list is silently misleading rather than harmless.
function* graphHierarchy(root) {
  const seen = new Set();
  const queue = [root];
  while (queue.length) {
    const graph = queue.pop();
    if (!graph || seen.has(graph)) continue;
    seen.add(graph);
    yield graph;

    if (graph.subgraphs instanceof Map) queue.push(...graph.subgraphs.values());
    for (const node of graph.nodes ?? []) {
      if (node?.isSubgraphNode?.()) queue.push(node.subgraph);
    }
  }
}

// Collect every `{name, url, directory}` the workflow knows about from the live graph.
//
// `node.properties.models` is the one copy that survives loading, so it is read straight off
// the graph. The workflow's TOP-LEVEL `models` array is not on the graph at all:
// `LGraph.configure()` does `this.extra = data.extra`, and `models` is a sibling of `extra`,
// so it is dropped. Reading `graph.extra.models` finds nothing — ever.
//
// ComfyUI runs that array through its own missing-model pipeline and caches the result, but
// where it caches it keeps moving: 1.45 hung it off
// `workflow.activeWorkflow.pendingWarnings.missingModelCandidates`, which 1.48 removed
// entirely (`pendingWarnings` appears nowhere in the bundle) in favour of a Pinia
// `missingModelStore` that is exposed on neither `window` nor `app`. There is no reachable
// replacement, so the index is graph-only — subgraphs included — and a missing URL is left to the
// backend, which resolves through CivitAI and HuggingFace anyway.
export function buildModelIndex(app) {
  const index = new Map();
  const add = (entry) => {
    const name = entry?.name;
    if (!name) return;
    if (!index.has(name)) index.set(name, []);
    index.get(name).push({ url: entry.url ?? '', directory: entry.directory ?? '' });
  };

  for (const graph of graphHierarchy(app?.rootGraph ?? app?.graph)) {
    for (const node of graph.nodes ?? []) {
      for (const model of node?.properties?.models ?? []) add(model);
    }
  }
  return index;
}

/** Pick the indexed entry for a filename, preferring one whose directory agrees. */
export function lookupModel(index, filename, directory) {
  const entries = index.get(filename) ?? [];
  return entries.find((e) => e.directory === directory) ?? entries[0] ?? null;
}

/**
 * Every row header in the panel, across the DOM shapes ComfyUI has shipped. The header is both
 * the element our button is appended to and the root the row is read from.
 */
export function collectRowHeaders(doc) {
  const headers = [];
  // >= 1.48: rows are direct children of a container, and the header is a row's first child.
  // Non-row children — the not-supported section's own heading block — carry no titled name
  // element and are dropped by readRow rather than special-cased here.
  for (const selector of ROW_CONTAINERS) {
    for (const container of doc.querySelectorAll(selector)) {
      for (const child of container.children) {
        if (child.firstElementChild) headers.push(child.firstElementChild);
      }
    }
  }
  // <= 1.45: the copy button sits in the name box, one level below the header.
  for (const copyButton of doc.querySelectorAll(LEGACY_ROW_ANCHOR)) {
    const header = copyButton.parentElement?.parentElement;
    if (header) headers.push(header);
  }
  return headers;
}

// Read one panel row: its filename, its directory and the header element to append to.
// Returns null when the row's directory cannot be established — those rows get no button,
// because guessing a folder is how a LoRA ends up in checkpoints.
//
// Both directory strategies are attempted on every row rather than switched on a detected
// version: each one reads a place the other's DOM does not have, so the wrong one simply finds
// nothing and falls through.
export function readRow(header, index) {
  // The model name is the first titled element in the header under either shape — a `p[title]`
  // in 1.45, a `button[title]`/`span[title]` in 1.48. The controls that follow it (link, copy
  // url, download) also carry titles, hence "first" and not "any".
  const nameNode = header?.querySelector('[title]');
  const filename = nameNode?.getAttribute('title')?.trim() ?? '';
  if (!filename) return null;

  // >= 1.48: name element → name row → name column, whose second line is the metadata label.
  const nameColumn = nameNode.parentElement?.parentElement;
  const label = nameColumn?.lastElementChild;
  const fromLabel =
    label && label !== nameNode.parentElement ? parseMetadataDirectory(label.textContent) : '';

  // <= 1.45: header → row root → rows container → group, whose first `p` is the heading.
  const group = header.parentElement?.parentElement?.parentElement;
  const fromHeading = fromLabel ? '' : parseGroupDirectory(group?.querySelector('p')?.textContent);

  // A scraped directory has already been held to the strict shape; one recovered from the
  // index came from workflow data rather than rendered text, so it keeps the looser check and
  // an unusual folder registered by a custom node is still honoured.
  const scraped = fromLabel || fromHeading;
  const indexed = lookupModel(index, filename, scraped);
  const directory = scraped || indexed?.directory || '';
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
  // The rows the last sync() saw. "Download all" reads this at click time rather than closing
  // over one sync's array: ACTIONS_MARK stops the button being re-injected, so a snapshot taken
  // when the actions bar rendered ahead of the rows would stay empty for the panel's lifetime.
  let currentRows = [];
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
    const seen = new Set();
    for (const header of collectRowHeaders(doc)) {
      const row = readRow(header, index);
      if (!row) continue;
      const key = taskKey(row.directory, row.filename);
      // A frontend that answers to more than one anchor style would otherwise report the same
      // row twice, and "Download all" would request it twice.
      if (seen.has(key)) continue;
      seen.add(key);
      rows.push(row);
      if (row.header.hasAttribute(ROW_MARK)) continue;
      row.header.setAttribute(ROW_MARK, '');

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
      currentRows = injectRows(buildModelIndex(app));
      injectDownloadAll(() => currentRows);
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
    currentRows = [];
    for (const marked of doc.querySelectorAll(`[${ROW_MARK}],[${ACTIONS_MARK}]`)) {
      marked.removeAttribute(ROW_MARK);
      marked.removeAttribute(ACTIONS_MARK);
    }
  }

  return { start, stop, sync };
}
