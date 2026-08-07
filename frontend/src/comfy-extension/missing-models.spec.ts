// Unit tests for the ComfyUI Missing Models integration (../../js/missing-models.js).
// The module lives outside src/ because ComfyUI loads it directly from web/, but it is written
// with injected dependencies precisely so it can be exercised here.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  createMissingModelsIntegration,
  buildModelIndex,
  lookupModel,
  parseGroupDirectory,
  readRow,
  taskKey,
  LABELS,
} from '../../js/missing-models.js';

const API = '/tiny-model-manager/api';

/** Rebuild the DOM shape of ComfyUI's MissingModelCard.vue / MissingModelRow.vue. */
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

function makeApp(nodes: unknown[] = []) {
  return {
    rootGraph: { nodes },
    refreshComboInNodes: vi.fn().mockResolvedValue(undefined),
    extensionManager: { toast: { add: vi.fn() } },
  };
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

  it('buildModelIndex also reads the workflow-level models array', () => {
    const app = {
      graph: { nodes: [], extra: { models: [{ name: 'c.ckpt', url: 'u3', directory: 'vae' }] } },
    };
    expect(buildModelIndex(app).get('c.ckpt')).toEqual([{ url: 'u3', directory: 'vae' }]);
  });

  it('buildModelIndex tolerates a graphless app', () => {
    expect(buildModelIndex({}).size).toBe(0);
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

  it('readRow returns the filename, directory and url', () => {
    renderPanel([{ directory: 'loras', files: ['a.safetensors'] }]);
    const copy = document.querySelector('[data-testid="missing-model-copy-name"]')!;
    const index = new Map([['a.safetensors', [{ url: 'u1', directory: 'loras' }]]]);
    const row = readRow(copy, index);
    expect(row).toMatchObject({ filename: 'a.safetensors', directory: 'loras', url: 'u1' });
  });
});

describe('button injection', () => {
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
