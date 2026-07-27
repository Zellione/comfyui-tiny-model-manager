// Unit tests for the ComfyUI extension's workflow-insert logic (../../../js/workflow-insert.js).
// The module lives outside src/ because ComfyUI loads it directly from web/, but it is written
// with injected dependencies precisely so it can be exercised here.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  createPendingProcessor,
  findWidgetOption,
  refreshComfyModels,
  stripSuffix,
} from '../../../js/workflow-insert.js';

const API = '/tiny-model-manager/api';

interface StubWidget {
  name: string;
  value?: string;
  options?: { values: string[] };
}

interface StubNode {
  widgets: StubWidget[];
  pos?: number[];
}

function makeNode(widgetName: string, values: string[] = []): StubNode {
  return { widgets: [{ name: widgetName, options: { values } }] };
}

function makeApp(overrides: Record<string, unknown> = {}) {
  return {
    refreshComboInNodes: vi.fn().mockResolvedValue(undefined),
    canvas: {
      canvas: { width: 800, height: 600 },
      ds: { offset: [0, 0], scale: 1 },
      selectNode: vi.fn(),
    },
    graph: { add: vi.fn(), setDirtyCanvas: vi.fn() },
    ...overrides,
  };
}

function makeFetch(pending: unknown[]) {
  return vi.fn().mockImplementation((url: string) => {
    if (url.endsWith('/workflow/pending')) {
      return Promise.resolve({ json: () => Promise.resolve({ success: true, data: pending }) });
    }
    return Promise.resolve({ json: () => Promise.resolve({ success: true }) });
  });
}

describe('stripSuffix', () => {
  it('removes ComfyUI’s " (N)" disambiguation suffix from the stem', () => {
    expect(stripSuffix('model (2).safetensors')).toBe('model.safetensors');
  });

  it('preserves the directory portion', () => {
    expect(stripSuffix('sdxl/model (10).safetensors')).toBe('sdxl/model.safetensors');
  });

  it('handles backslash separators and files without an extension', () => {
    expect(stripSuffix('sdxl\\model (3)')).toBe('sdxl\\model');
  });

  it('leaves untouched names unchanged', () => {
    expect(stripSuffix('model.safetensors')).toBe('model.safetensors');
  });
});

describe('findWidgetOption', () => {
  it('returns the filename when the widget offers it verbatim', () => {
    const widget = { name: 'ckpt_name', options: { values: ['a.safetensors', 'b.safetensors'] } };
    expect(findWidgetOption(widget, 'b.safetensors')).toBe('b.safetensors');
  });

  it('matches an option that carries a suffix we do not have', () => {
    const widget = { name: 'ckpt_name', options: { values: ['model (2).safetensors'] } };
    expect(findWidgetOption(widget, 'model.safetensors')).toBe('model (2).safetensors');
  });

  it('matches a suffix-free option when our filename carries a suffix', () => {
    const widget = { name: 'ckpt_name', options: { values: ['model.safetensors'] } };
    expect(findWidgetOption(widget, 'model (2).safetensors')).toBe('model.safetensors');
  });

  it('falls back to the filename when nothing matches', () => {
    const widget = { name: 'ckpt_name', options: { values: ['other.safetensors'] } };
    expect(findWidgetOption(widget, 'model.safetensors')).toBe('model.safetensors');
  });

  it('tolerates a widget with no options', () => {
    expect(findWidgetOption({ name: 'ckpt_name' }, 'model.safetensors')).toBe('model.safetensors');
  });
});

describe('refreshComfyModels', () => {
  it('awaits refreshComboInNodes when available', async () => {
    const app = makeApp();
    await refreshComfyModels(app);
    expect(app.refreshComboInNodes).toHaveBeenCalledOnce();
  });

  it('swallows a rejected refresh', async () => {
    const app = makeApp({ refreshComboInNodes: vi.fn().mockRejectedValue(new Error('offline')) });
    await expect(refreshComfyModels(app)).resolves.toBeUndefined();
  });

  it('is a no-op on frontends that do not expose it', async () => {
    await expect(refreshComfyModels({})).resolves.toBeUndefined();
    await expect(refreshComfyModels(undefined)).resolves.toBeUndefined();
  });
});

describe('createPendingProcessor', () => {
  let liteGraph: { createNode: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    liteGraph = { createNode: vi.fn().mockImplementation(() => makeNode('ckpt_name')) };
  });

  it('refreshes ComfyUI models before creating the node', async () => {
    const order: string[] = [];
    const app = makeApp({
      refreshComboInNodes: vi.fn().mockImplementation(async () => {
        order.push('refresh');
      }),
    });
    liteGraph.createNode.mockImplementation(() => {
      order.push('createNode');
      return makeNode('ckpt_name');
    });
    const fetchFn = makeFetch([{ id: '1', model_type: 'checkpoints', filename: 'a.safetensors' }]);

    await createPendingProcessor({ app, liteGraph, api: API, fetchFn })();

    expect(order).toEqual(['refresh', 'createNode']);
  });

  it('refreshes once per batch, not once per item', async () => {
    const app = makeApp();
    const fetchFn = makeFetch([
      { id: '1', model_type: 'checkpoints', filename: 'a.safetensors' },
      { id: '2', model_type: 'loras', filename: 'b.safetensors' },
    ]);

    await createPendingProcessor({ app, liteGraph, api: API, fetchFn })();

    expect(app.refreshComboInNodes).toHaveBeenCalledOnce();
    expect(app.graph.add).toHaveBeenCalledTimes(2);
  });

  it('does not refresh when nothing is pending', async () => {
    const app = makeApp();
    const fetchFn = makeFetch([]);

    await createPendingProcessor({ app, liteGraph, api: API, fetchFn })();

    expect(app.refreshComboInNodes).not.toHaveBeenCalled();
    expect(liteGraph.createNode).not.toHaveBeenCalled();
  });

  it('still inserts the node when the refresh rejects', async () => {
    const app = makeApp({ refreshComboInNodes: vi.fn().mockRejectedValue(new Error('offline')) });
    const fetchFn = makeFetch([{ id: '1', model_type: 'checkpoints', filename: 'a.safetensors' }]);

    await createPendingProcessor({ app, liteGraph, api: API, fetchFn })();

    expect(app.graph.add).toHaveBeenCalledOnce();
  });

  it('still inserts the node on frontends without refreshComboInNodes', async () => {
    const app = makeApp({ refreshComboInNodes: undefined });
    const fetchFn = makeFetch([{ id: '1', model_type: 'checkpoints', filename: 'a.safetensors' }]);

    await createPendingProcessor({ app, liteGraph, api: API, fetchFn })();

    expect(app.graph.add).toHaveBeenCalledOnce();
  });

  it('ignores an overlapping tick while a refresh is in flight', async () => {
    let releaseRefresh: () => void = () => undefined;
    const app = makeApp({
      refreshComboInNodes: vi.fn().mockImplementation(
        () =>
          new Promise<void>((resolve) => {
            releaseRefresh = resolve;
          }),
      ),
    });
    const fetchFn = makeFetch([{ id: '1', model_type: 'checkpoints', filename: 'a.safetensors' }]);
    const processPending = createPendingProcessor({ app, liteGraph, api: API, fetchFn });

    const first = processPending();
    await Promise.resolve();
    await processPending(); // second tick lands mid-refresh and must bail out
    releaseRefresh();
    await first;

    expect(app.refreshComboInNodes).toHaveBeenCalledOnce();
    expect(app.graph.add).toHaveBeenCalledOnce();
  });

  it('runs again on a later tick once the previous one finished', async () => {
    const app = makeApp();
    const fetchFn = makeFetch([{ id: '1', model_type: 'checkpoints', filename: 'a.safetensors' }]);
    const processPending = createPendingProcessor({ app, liteGraph, api: API, fetchFn });

    await processPending();
    await processPending();

    expect(app.graph.add).toHaveBeenCalledTimes(2);
  });

  it('acks the item after inserting it', async () => {
    const app = makeApp();
    const fetchFn = makeFetch([
      { id: 'abc', model_type: 'checkpoints', filename: 'a.safetensors' },
    ]);

    await createPendingProcessor({ app, liteGraph, api: API, fetchFn })();

    expect(fetchFn).toHaveBeenCalledWith(
      `${API}/workflow/ack`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ id: 'abc' }) }),
    );
  });

  it('resolves the widget value through the refreshed option list', async () => {
    const app = makeApp();
    const node = makeNode('ckpt_name', ['model (2).safetensors']);
    liteGraph.createNode.mockReturnValue(node);
    const fetchFn = makeFetch([
      { id: '1', model_type: 'checkpoints', filename: 'model.safetensors' },
    ]);

    await createPendingProcessor({ app, liteGraph, api: API, fetchFn })();

    expect(node.widgets[0].value).toBe('model (2).safetensors');
  });

  it('skips items with an unknown model type', async () => {
    const app = makeApp();
    const fetchFn = makeFetch([{ id: '1', model_type: 'unknown_type', filename: 'a.safetensors' }]);

    await createPendingProcessor({ app, liteGraph, api: API, fetchFn })();

    expect(liteGraph.createNode).not.toHaveBeenCalled();
    expect(app.graph.add).not.toHaveBeenCalled();
  });

  it('skips items whose node type cannot be created', async () => {
    const app = makeApp();
    liteGraph.createNode.mockReturnValue(null);
    const fetchFn = makeFetch([{ id: '1', model_type: 'checkpoints', filename: 'a.safetensors' }]);

    await createPendingProcessor({ app, liteGraph, api: API, fetchFn })();

    expect(app.graph.add).not.toHaveBeenCalled();
  });

  it('returns quietly when the pending request fails, leaving the guard released', async () => {
    const app = makeApp();
    const fetchFn = vi.fn().mockRejectedValue(new Error('network down'));
    const processPending = createPendingProcessor({ app, liteGraph, api: API, fetchFn });

    await expect(processPending()).resolves.toBeUndefined();
    await processPending();

    expect(fetchFn).toHaveBeenCalledTimes(2);
    expect(app.refreshComboInNodes).not.toHaveBeenCalled();
  });

  it('places the node at the viewport centre', async () => {
    const app = makeApp();
    app.canvas.ds = { offset: [100, 50], scale: 2 };
    const node = makeNode('ckpt_name');
    liteGraph.createNode.mockReturnValue(node);
    const fetchFn = makeFetch([{ id: '1', model_type: 'checkpoints', filename: 'a.safetensors' }]);

    await createPendingProcessor({ app, liteGraph, api: API, fetchFn })();

    expect(node.pos).toEqual([(800 / 2 - 100) / 2, (600 / 2 - 50) / 2]);
  });
});
