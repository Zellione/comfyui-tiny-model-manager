// Unit tests for the ComfyUI Missing Models integration (../../js/missing-models.js).
// The module lives outside src/ because ComfyUI loads it directly from web/, but it is written
// with injected dependencies precisely so it can be exercised here.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  createMissingModelsIntegration,
  buildModelIndex,
  collectRowHeaders,
  lookupModel,
  parseGroupDirectory,
  parseMetadataDirectory,
  readRow,
  taskKey,
  LABELS,
} from '../../js/missing-models.js';

const API = '/tiny-model-manager/api';

/**
 * Rebuild the DOM shape of ComfyUI frontend >= 1.48: one flat row list inside a container,
 * each row printing its own "<directory> · <size>" metadata line. No per-row testid exists in
 * this shape, and no category headings.
 */
function renderPanel148(
  rows: { directory: string | null; filename: string; size?: string }[],
  withActions = true,
) {
  const panel = document.createElement('div');
  const container = document.createElement('div');
  container.setAttribute('data-testid', 'missing-model-importable-rows');

  for (const { directory, filename, size = '6.86 GB' } of rows) {
    const root = document.createElement('div');
    const header = document.createElement('div');

    const nameColumn = document.createElement('span');
    const nameRow = document.createElement('span');
    const name = document.createElement('button');
    name.setAttribute('title', filename);
    name.textContent = filename;
    const link = document.createElement('button');
    link.setAttribute('title', 'Copy link');
    nameRow.append(name, link);
    // `directory: null` renders the localized unknown-category placeholder instead.
    const label = document.createElement('span');
    label.textContent = `${directory ?? 'Unknown'} · ${size}`;
    nameColumn.append(nameRow, label);

    header.appendChild(nameColumn);
    root.appendChild(header);
    container.appendChild(root);
  }
  panel.appendChild(container);

  if (withActions) {
    const actions = document.createElement('div');
    actions.setAttribute('data-testid', 'missing-model-actions');
    panel.appendChild(actions);
  }

  document.body.appendChild(panel);
  return { panel, container };
}

/** Rebuild the DOM shape of ComfyUI frontend <= 1.45: rows grouped under category headings. */
function renderPanel(groups: { directory: string; files: string[] }[], withActions = true) {
  const panel = document.createElement('div');
  if (withActions) {
    const actions = document.createElement('div');
    actions.setAttribute('data-testid', 'missing-model-actions');
    panel.appendChild(actions);
  }

  for (const group of groups) {
    const groupEl = document.createElement('div');
    const heading = document.createElement('div');
    const headingText = document.createElement('p');
    headingText.textContent = `${group.directory} (${group.files.length})`;
    heading.appendChild(headingText);
    groupEl.appendChild(heading);

    const rows = document.createElement('div');
    for (const filename of group.files) {
      const root = document.createElement('div');
      const header = document.createElement('div');
      const nameBox = document.createElement('div');
      const name = document.createElement('p');
      name.setAttribute('title', filename);
      name.textContent = `${filename} (1)`;
      const copy = document.createElement('button');
      copy.setAttribute('data-testid', 'missing-model-copy-name');
      nameBox.append(name, copy);
      header.appendChild(nameBox);
      root.appendChild(header);
      rows.appendChild(root);
    }
    groupEl.appendChild(rows);
    panel.appendChild(groupEl);
  }

  document.body.appendChild(panel);
  return panel;
}

function tmmButtons() {
  return Array.from(document.querySelectorAll<HTMLButtonElement>('.tmm-missing-btn'));
}

function rowButtons() {
  return tmmButtons().filter((b) => b.textContent !== LABELS.all);
}

function makeApp(nodes: unknown[] = [], graphExtras: Record<string, unknown> = {}) {
  return {
    rootGraph: { nodes, ...graphExtras },
    refreshComboInNodes: vi.fn().mockResolvedValue(undefined),
    extensionManager: { toast: { add: vi.fn() } },
  };
}

/** A litegraph Subgraph: the traversal only ever reads `nodes` off one. */
function subgraph(nodes: unknown[]) {
  return { nodes };
}

/** A node instantiating `sub` — the shape ComfyUI's own `forEachNode` recurses through. */
function subgraphNode(sub: unknown) {
  return { isSubgraphNode: () => true, subgraph: sub };
}

/** fetch stub: POST /download/missing answers with `missing`, GET /download/status with `tasks`. */
function makeFetch(missing: unknown = { success: true, data: { task_id: 't1' } }, tasks = []) {
  return vi.fn().mockImplementation((url: string) => {
    const body = url.endsWith('/download/status') ? { success: true, data: tasks } : missing;
    return Promise.resolve({ json: () => Promise.resolve(body) });
  });
}

function build(overrides: Record<string, unknown> = {}) {
  return createMissingModelsIntegration({
    app: makeApp(),
    api: API,
    fetchFn: makeFetch(),
    doc: document,
    openWindow: vi.fn(),
    ...overrides,
  });
}

afterEach(() => {
  document.body.innerHTML = '';
  vi.useRealTimers();
});

describe('pure helpers', () => {
  it('taskKey namespaces a filename by its directory', () => {
    expect(taskKey('loras', 'a.safetensors')).toBe('loras::a.safetensors');
  });

  it.each([
    ['checkpoints (2)', 'checkpoints'],
    ['text_encoders (11)', 'text_encoders'],
    ['  loras (1)  ', 'loras'],
    ['Unknown category (3)', ''],
    ['loras', ''],
    ['', ''],
    [undefined, ''],
  ])('parseGroupDirectory(%p) → %p', (input, expected) => {
    expect(parseGroupDirectory(input as string)).toBe(expected);
  });

  it('buildModelIndex collects node properties.models', () => {
    const app = makeApp([
      { properties: { models: [{ name: 'a.safetensors', url: 'u1', directory: 'loras' }] } },
      { properties: { models: [{ name: 'b.safetensors', url: 'u2', directory: 'vae' }] } },
      { properties: {} },
      {},
    ]);
    const index = buildModelIndex(app);
    expect(index.get('a.safetensors')).toEqual([{ url: 'u1', directory: 'loras' }]);
    expect(index.get('b.safetensors')).toEqual([{ url: 'u2', directory: 'vae' }]);
  });

  // Comfy-Org's templates have moved their loaders into subgraphs, and a root-only walk finds
  // nothing there. The Wan 2.2 T2V template's root graph holds two notes, one subgraph instance
  // and SaveVideo; all six models sit in `definitions.subgraphs[0].nodes[].properties.models`.
  // Every row was therefore posted with `url: ''`, which skips the resolver's URL stage *and* its
  // raw-URL last resort, leaving only provider searches that cannot match a Comfy-Org repack — so
  // the panel offered "Search in TMM" for models whose exact URL the workflow was carrying (#150).
  it('buildModelIndex descends into a subgraph instance node', () => {
    const app = makeApp([
      {},
      subgraphNode(
        subgraph([
          { properties: { models: [{ name: 'wan.safetensors', url: 'u1', directory: 'loras' }] } },
        ]),
      ),
    ]);
    expect(buildModelIndex(app).get('wan.safetensors')).toEqual([
      { url: 'u1', directory: 'loras' },
    ]);
  });

  // `LGraph.get subgraphs()` returns `rootGraph._subgraphs`, a registry of every subgraph at any
  // depth. ComfyUI's `findSubgraphByUuid` prefers it over recursion for exactly that reason.
  it('buildModelIndex reads the rootGraph subgraph registry', () => {
    const app = makeApp([], {
      subgraphs: new Map([
        [
          'uuid-1',
          subgraph([
            { properties: { models: [{ name: 'vae.safetensors', url: 'u2', directory: 'vae' }] } },
          ]),
        ],
      ]),
    });
    expect(buildModelIndex(app).get('vae.safetensors')).toEqual([{ url: 'u2', directory: 'vae' }]);
  });

  it('buildModelIndex descends into nested subgraphs', () => {
    const inner = subgraph([
      { properties: { models: [{ name: 'deep.safetensors', url: 'u3', directory: 'loras' }] } },
    ]);
    const app = makeApp([subgraphNode(subgraph([subgraphNode(inner)]))]);
    expect(buildModelIndex(app).get('deep.safetensors')).toEqual([
      { url: 'u3', directory: 'loras' },
    ]);
  });

  // `lookupModel` returns `entries[0]`, so a subgraph visited twice would silently stack duplicate
  // entries behind one filename. Both routes into the hierarchy are live at once, and the registry
  // holds the same object the instance node points at.
  it('buildModelIndex indexes a subgraph reachable both ways only once', () => {
    const sub = subgraph([
      { properties: { models: [{ name: 'both.safetensors', url: 'u4', directory: 'vae' }] } },
    ]);
    const app = makeApp([subgraphNode(sub)], { subgraphs: new Map([['uuid-1', sub]]) });
    expect(buildModelIndex(app).get('both.safetensors')).toHaveLength(1);
  });

  // ComfyUI's own forEachNode has no cycle guard; a subgraph instantiating itself would hang the
  // browser. `buildSubgraphExecutionPaths` keeps a visited set for the same reason.
  it('buildModelIndex terminates on a self-referencing subgraph', () => {
    const sub: { nodes: unknown[] } = {
      nodes: [
        { properties: { models: [{ name: 'loop.safetensors', url: 'u5', directory: 'loras' }] } },
      ],
    };
    sub.nodes.push(subgraphNode(sub));
    const app = makeApp([subgraphNode(sub)]);
    expect(buildModelIndex(app).get('loop.safetensors')).toHaveLength(1);
  });

  // Pins the finding rather than the old assumption: LGraph.configure() assigns only
  // `data.extra`, so a workflow's top-level `models` array never lands under `graph.extra`.
  // Reading it there looked like it worked and silently found nothing. Do not "restore" it —
  // the reachable copy is the cached candidate list asserted above.
  it('buildModelIndex does not rely on graph.extra.models, which never carries them', () => {
    const app = {
      graph: { nodes: [], extra: { models: [{ name: 'c.ckpt', url: 'u3', directory: 'vae' }] } },
    };
    expect(buildModelIndex(app).size).toBe(0);
  });

  it('buildModelIndex tolerates a graphless app', () => {
    expect(buildModelIndex({}).size).toBe(0);
  });

  // ComfyUI caches the resolved candidate list, but where it caches it keeps moving: 1.45 hung
  // it off `workflow.activeWorkflow.pendingWarnings.missingModelCandidates`, and 1.48 removed
  // `pendingWarnings` entirely in favour of a Pinia store exposed on neither `window` nor
  // `app`. Reading a cache that no longer exists is not a fallback, so the index is graph-only
  // and a row with no URL is left to the backend's provider search.
  it('buildModelIndex ignores an unreachable candidate cache', () => {
    const app = {
      rootGraph: { nodes: [] },
      extensionManager: {
        workflow: {
          activeWorkflow: {
            pendingWarnings: { missingModelCandidates: [{ name: 'x.safetensors', url: 'u' }] },
          },
        },
      },
    };
    expect(buildModelIndex(app).size).toBe(0);
  });

  it('lookupModel prefers the entry whose directory agrees', () => {
    const index = new Map([
      [
        'a.safetensors',
        [
          { url: 'ckpt', directory: 'checkpoints' },
          { url: 'lora', directory: 'loras' },
        ],
      ],
    ]);
    expect(lookupModel(index, 'a.safetensors', 'loras')?.url).toBe('lora');
    expect(lookupModel(index, 'a.safetensors', 'vae')?.url).toBe('ckpt');
    expect(lookupModel(index, 'missing', 'vae')).toBeNull();
  });

  it.each([
    ['checkpoints · 6.86 GB', 'checkpoints'],
    ['text_encoders · 120 MB', 'text_encoders'],
    ['loras', 'loras'],
    // The localized unknown-category placeholder shares this slot with a real folder name.
    ['Unknown · 6.86 GB', ''],
    ['Desconocido · 6.86 GB', ''],
    ['Неизвестно · 6.86 GB', ''],
    ['', ''],
    [undefined, ''],
  ])('parseMetadataDirectory(%p) → %p', (input, expected) => {
    expect(parseMetadataDirectory(input as string)).toBe(expected);
  });

  it('readRow reads a 1.45 grouped row', () => {
    renderPanel([{ directory: 'loras', files: ['a.safetensors'] }]);
    const index = new Map([['a.safetensors', [{ url: 'u1', directory: 'loras' }]]]);
    const [header] = collectRowHeaders(document);
    expect(readRow(header, index)).toMatchObject({
      filename: 'a.safetensors',
      directory: 'loras',
      url: 'u1',
    });
  });

  it('readRow reads a 1.48 flat row from its own metadata line', () => {
    renderPanel148([{ directory: 'checkpoints', filename: 'hunyuan_3d_v2.1.safetensors' }]);
    const index = new Map([
      ['hunyuan_3d_v2.1.safetensors', [{ url: 'u1', directory: 'checkpoints' }]],
    ]);
    const [header] = collectRowHeaders(document);
    expect(readRow(header, index)).toMatchObject({
      filename: 'hunyuan_3d_v2.1.safetensors',
      directory: 'checkpoints',
      url: 'u1',
    });
  });

  // The row still renders, so it must be rejected rather than simply not found.
  it('readRow rejects a 1.48 row whose category is unknown', () => {
    renderPanel148([{ directory: null, filename: 'mystery.safetensors' }]);
    const [header] = collectRowHeaders(document);
    expect(readRow(header, new Map())).toBeNull();
  });

  // The graph knows the folder even when the panel does not print a usable one.
  it('readRow falls back to the model index when the label is unparseable', () => {
    renderPanel148([{ directory: null, filename: 'mystery.safetensors' }]);
    const index = new Map([
      ['mystery.safetensors', [{ url: 'u9', directory: 'diffusion_models' }]],
    ]);
    const [header] = collectRowHeaders(document);
    expect(readRow(header, index)).toMatchObject({
      directory: 'diffusion_models',
      url: 'u9',
    });
  });
});

describe('button injection', () => {
  // Regression for the reported bug: 1.48 removed `missing-model-copy-name`, the integration's
  // only row anchor, so no row button was injected and "Download all with TMM" looped over an
  // empty list. `missing-model-actions` survived, which is why that button still rendered.
  it('adds one button per row on the 1.48 panel', () => {
    renderPanel148([
      { directory: 'checkpoints', filename: 'hunyuan_3d_v2.1.safetensors' },
      { directory: 'loras', filename: 'b.safetensors' },
    ]);
    build().sync();
    expect(rowButtons()).toHaveLength(2);
    expect(tmmButtons().filter((b) => b.textContent === LABELS.all)).toHaveLength(1);
  });

  it('posts the filename and directory read off a 1.48 row', async () => {
    renderPanel148([{ directory: 'checkpoints', filename: 'hunyuan_3d_v2.1.safetensors' }]);
    const fetchFn = makeFetch();
    build({ fetchFn }).sync();
    rowButtons()[0].click();
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalled());
    expect(JSON.parse(fetchFn.mock.calls[0][1].body)).toMatchObject({
      filename: 'hunyuan_3d_v2.1.safetensors',
      directory: 'checkpoints',
    });
  });

  // The user-visible half of #150: the index tests above would still pass if `readRow` stopped
  // threading the url through, and the panel would go back to answering "Search in TMM".
  it('posts the url of a model that only exists inside a subgraph', async () => {
    renderPanel148([
      {
        directory: 'loras',
        filename: 'wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors',
      },
    ]);
    const fetchFn = makeFetch();
    const app = makeApp([
      subgraphNode(
        subgraph([
          {
            properties: {
              models: [
                {
                  name: 'wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors',
                  url: 'https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors',
                  directory: 'loras',
                },
              ],
            },
          },
        ]),
      ),
    ]);
    build({ fetchFn, app }).sync();
    rowButtons()[0].click();
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalled());
    expect(JSON.parse(fetchFn.mock.calls[0][1].body)).toMatchObject({
      filename: 'wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors',
      directory: 'loras',
      url: 'https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors',
    });
  });

  it('skips a 1.48 row whose category is unknown', () => {
    renderPanel148([{ directory: null, filename: 'mystery.safetensors' }]);
    build().sync();
    expect(rowButtons()).toHaveLength(0);
  });

  // Both anchor styles resolving to the same row must not yield two buttons or two downloads.
  it('does not double-count a row reachable through both anchor styles', () => {
    renderPanel([{ directory: 'loras', files: ['a.safetensors'] }]);
    const copy = document.querySelector('[data-testid="missing-model-copy-name"]')!;
    const rowsContainer = copy.parentElement!.parentElement!.parentElement!;
    rowsContainer.setAttribute('data-testid', 'missing-model-importable-rows');
    build().sync();
    expect(rowButtons()).toHaveLength(1);
  });

  // The actions bar can render before any row does. ACTIONS_MARK then blocks re-injection, so a
  // list captured at injection time would stay empty for the panel's lifetime.
  it('download-all uses the rows present at click time, not at injection time', async () => {
    renderPanel148([], true);
    const fetchFn = makeFetch();
    const integration = build({ fetchFn });
    integration.sync();

    const actions = document.querySelector('[data-testid="missing-model-actions"]')!;
    document.body.innerHTML = '';
    const { panel } = renderPanel148(
      [{ directory: 'checkpoints', filename: 'late.safetensors' }],
      false,
    );
    panel.appendChild(actions);
    integration.sync();

    tmmButtons()
      .find((b) => b.textContent === LABELS.all)!
      .click();
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalled());
    expect(JSON.parse(fetchFn.mock.calls[0][1].body)).toMatchObject({
      filename: 'late.safetensors',
    });
  });

  it('adds one button per row plus the download-all button', () => {
    renderPanel([
      { directory: 'loras', files: ['a.safetensors', 'b.safetensors'] },
      { directory: 'vae', files: ['c.safetensors'] },
    ]);
    build().sync();
    expect(rowButtons()).toHaveLength(3);
    expect(tmmButtons().filter((b) => b.textContent === LABELS.all)).toHaveLength(1);
  });

  it('is idempotent across repeated syncs', () => {
    renderPanel([{ directory: 'loras', files: ['a.safetensors'] }]);
    const integration = build();
    integration.sync();
    integration.sync();
    integration.sync();
    expect(tmmButtons()).toHaveLength(2);
  });

  it('injects into rows Vue re-rendered after the first sync', () => {
    renderPanel([{ directory: 'loras', files: ['a.safetensors'] }]);
    const integration = build();
    integration.sync();
    document.body.innerHTML = '';
    renderPanel([{ directory: 'loras', files: ['a.safetensors'] }]);
    integration.sync();
    expect(rowButtons()).toHaveLength(1);
  });

  it('skips rows whose directory cannot be established', () => {
    renderPanel([{ directory: 'Unknown category', files: ['a.safetensors'] }]);
    build().sync();
    expect(rowButtons()).toHaveLength(0);
  });

  it('falls back to the indexed directory when the heading is unusable', () => {
    renderPanel([{ directory: 'Unknown category', files: ['a.safetensors'] }]);
    const app = makeApp([
      { properties: { models: [{ name: 'a.safetensors', url: 'u1', directory: 'loras' }] } },
    ]);
    build({ app }).sync();
    expect(rowButtons()).toHaveLength(1);
  });

  it('tolerates a panel without the actions header', () => {
    renderPanel([{ directory: 'loras', files: ['a.safetensors'] }], false);
    build().sync();
    expect(tmmButtons()).toHaveLength(1);
  });

  it('stop() removes the buttons and the markers so a later start() re-injects', () => {
    renderPanel([{ directory: 'loras', files: ['a.safetensors'] }]);
    const integration = build();
    integration.start();
    expect(tmmButtons()).toHaveLength(2);
    integration.stop();
    expect(tmmButtons()).toHaveLength(0);
    integration.start();
    expect(tmmButtons()).toHaveLength(2);
    integration.stop();
  });
});

describe('download requests', () => {
  beforeEach(() => {
    renderPanel([{ directory: 'loras', files: ['a.safetensors'] }]);
  });

  it('posts the filename, directory and url', async () => {
    const fetchFn = makeFetch();
    const app = makeApp([
      { properties: { models: [{ name: 'a.safetensors', url: 'u1', directory: 'loras' }] } },
    ]);
    const integration = build({ fetchFn, app });
    integration.sync();
    rowButtons()[0].click();
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalled());

    expect(fetchFn).toHaveBeenCalledWith(
      `${API}/download/missing`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ filename: 'a.safetensors', directory: 'loras', url: 'u1' }),
      }),
    );
    integration.stop();
  });

  it('shows the installed state without queueing', async () => {
    const fetchFn = makeFetch({ success: true, data: { already_installed: true } });
    const integration = build({ fetchFn });
    integration.sync();
    rowButtons()[0].click();
    await vi.waitFor(() => expect(rowButtons()[0].textContent).toBe(LABELS.installed));
    expect(rowButtons()[0].disabled).toBe(true);
    integration.stop();
  });

  it('offers a dashboard search when nothing resolved', async () => {
    const fetchFn = makeFetch({
      success: true,
      data: { unresolved: true, search_term: 'My_Lora', model_type: 'loras' },
    });
    const openWindow = vi.fn();
    const integration = build({ fetchFn, openWindow });
    integration.sync();
    rowButtons()[0].click();
    await vi.waitFor(() => expect(rowButtons()[0].textContent).toBe(LABELS.search));

    rowButtons()[0].click();
    await vi.waitFor(() => expect(openWindow).toHaveBeenCalled());
    expect(openWindow).toHaveBeenCalledWith(
      '/tiny-model-manager/download?q=My_Lora&platform=civitai&type=loras',
    );
    integration.stop();
  });

  it('marks the button failed and toasts when the backend rejects', async () => {
    const fetchFn = makeFetch({ success: false, error: 'unsupported_directory' });
    const app = makeApp();
    const integration = build({ fetchFn, app });
    integration.sync();
    rowButtons()[0].click();
    await vi.waitFor(() => expect(rowButtons()[0].textContent).toBe(LABELS.failed));
    expect(app.extensionManager.toast.add).toHaveBeenCalledWith(
      expect.objectContaining({ severity: 'error' }),
    );
    integration.stop();
  });

  it('marks the button failed when fetch itself throws', async () => {
    const fetchFn = vi.fn().mockRejectedValue(new Error('offline'));
    const integration = build({ fetchFn });
    integration.sync();
    rowButtons()[0].click();
    await vi.waitFor(() => expect(rowButtons()[0].textContent).toBe(LABELS.failed));
    integration.stop();
  });
});

describe('progress polling', () => {
  it('shows progress, then done, and refreshes ComfyUI model lists', async () => {
    renderPanel([{ directory: 'loras', files: ['a.safetensors'] }]);
    const app = makeApp();
    let tasks: unknown[] = [{ id: 't1', status: 'downloading', progress: 42 }];
    const fetchFn = vi.fn().mockImplementation((url: string) => {
      const body = url.endsWith('/download/status')
        ? { success: true, data: tasks }
        : { success: true, data: { task_id: 't1' } };
      return Promise.resolve({ json: () => Promise.resolve(body) });
    });

    const integration = build({ fetchFn, app });
    integration.sync();
    rowButtons()[0].click();
    await vi.waitFor(() => expect(rowButtons()[0].textContent).toBe('TMM 42%'));

    tasks = [{ id: 't1', status: 'done', progress: 100 }];
    await vi.waitFor(() => expect(rowButtons()[0].textContent).toBe(LABELS.done));
    expect(app.refreshComboInNodes).toHaveBeenCalled();
    integration.stop();
  });

  it('surfaces a failed transfer', async () => {
    renderPanel([{ directory: 'loras', files: ['a.safetensors'] }]);
    const fetchFn = makeFetch({ success: true, data: { task_id: 't1' } }, [
      { id: 't1', status: 'error', error: 'HTTP 403' },
    ] as never);
    const integration = build({ fetchFn });
    integration.sync();
    rowButtons()[0].click();
    await vi.waitFor(() => expect(rowButtons()[0].textContent).toBe(LABELS.failed));
    expect(rowButtons()[0].title).toBe('HTTP 403');
    integration.stop();
  });

  it('treats a task the backend has forgotten as finished', async () => {
    renderPanel([{ directory: 'loras', files: ['a.safetensors'] }]);
    const integration = build({ fetchFn: makeFetch() });
    integration.sync();
    rowButtons()[0].click();
    await vi.waitFor(() => expect(rowButtons()[0].textContent).toBe(LABELS.done));
    integration.stop();
  });
});

describe('download all', () => {
  it('requests every row once, sequentially', async () => {
    renderPanel([
      { directory: 'loras', files: ['a.safetensors', 'b.safetensors'] },
      { directory: 'vae', files: ['c.safetensors'] },
    ]);
    const fetchFn = makeFetch();
    const integration = build({ fetchFn });
    integration.sync();

    tmmButtons()
      .find((b) => b.textContent === LABELS.all)!
      .click();
    await vi.waitFor(() => {
      const posts = fetchFn.mock.calls.filter((c) => String(c[0]).endsWith('/download/missing'));
      expect(posts).toHaveLength(3);
    });
    integration.stop();
  });
});
