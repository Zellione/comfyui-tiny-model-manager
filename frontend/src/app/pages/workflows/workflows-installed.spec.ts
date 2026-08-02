import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { WorkflowsInstalled } from './workflows-installed';
import { StoredWorkflow, WorkflowEntry, WorkflowStoreService } from '../../services/workflow-store';
import { NotificationService } from '../../services/notification';

const mockStore = {
  list: vi.fn(),
  deleteEntry: vi.fn(),
  exportWorkflow: vi.fn(),
  openInComfy: vi.fn(),
  fileUrl: vi.fn((id: number) => `/tiny-model-manager/api/workflows/${id}/file`),
};
const mockNotifService = { show: vi.fn() };

function makeWorkflow(id = 1, overrides: Partial<StoredWorkflow> = {}): StoredWorkflow {
  return {
    id,
    entry_id: 10,
    name: `graph-${id}`,
    local_path: `hash/7/graph-${id}.json`,
    version_id: '7',
    version_name: 'v1',
    node_count: 12,
    ...overrides,
  };
}

function makeEntry(id = 10, overrides: Partial<WorkflowEntry> = {}): WorkflowEntry {
  return {
    id,
    source_platform: 'civitai',
    source_page_id: '123',
    source_page_url: 'https://civitai.com/models/123',
    display_name: 'Cool Pack',
    description: '',
    base_model: 'Flux.1 D',
    tags: ['comfyui'],
    thumbnail_url: 'https://img/remote.jpg',
    media_hash: 'hash',
    items: [makeWorkflow(1), makeWorkflow(2)],
    media: [],
    ...overrides,
  };
}

async function createFixture() {
  await TestBed.configureTestingModule({
    imports: [WorkflowsInstalled],
    providers: [
      { provide: WorkflowStoreService, useValue: mockStore },
      { provide: NotificationService, useValue: mockNotifService },
      provideTranslateServiceForTests(),
    ],
  }).compileComponents();
  return TestBed.createComponent(WorkflowsInstalled);
}

async function createComponent() {
  return (await createFixture()).componentInstance;
}

/** Render and settle, so the template itself is exercised rather than only the class. */
async function render() {
  const fixture = await createFixture();
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
  return fixture;
}

describe('WorkflowsInstalled', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStore.list.mockReturnValue(of([]));
    mockStore.deleteEntry.mockReturnValue(of(void 0));
    mockStore.exportWorkflow.mockReturnValue(of({ path: '/user/default/workflows/a.json' }));
    mockStore.openInComfy.mockReturnValue(of({ id: 'uuid' }));
    mockStore.fileUrl.mockImplementation(
      (id: number) => `/tiny-model-manager/api/workflows/${id}/file`,
    );
  });

  it('loads entries on construction', async () => {
    mockStore.list.mockReturnValue(of([makeEntry()]));
    const c = await createComponent();
    expect(c.entries()).toHaveLength(1);
    expect(c.loading()).toBe(false);
    expect(c.error()).toBe('');
  });

  it('counts graphs across every entry', async () => {
    mockStore.list.mockReturnValue(
      of([makeEntry(10), makeEntry(11, { items: [makeWorkflow(3)] })]),
    );
    const c = await createComponent();
    expect(c.totalGraphs()).toBe(3);
  });

  it('sets error when the list request fails', async () => {
    mockStore.list.mockReturnValue(
      throwError(() => new HttpErrorResponse({ error: { error: 'db down' } })),
    );
    const c = await createComponent();
    expect(c.error()).toBe('db down');
    expect(c.loading()).toBe(false);
  });

  it('reloads on retry', async () => {
    const c = await createComponent();
    mockStore.list.mockReturnValue(of([makeEntry()]));
    c.load();
    expect(c.entries()).toHaveLength(1);
  });

  it('queues a graph for ComfyUI and notifies', async () => {
    const c = await createComponent();
    c.loadInComfy(makeWorkflow(1));
    expect(mockStore.openInComfy).toHaveBeenCalledWith(1);
    expect(c.busyWorkflowId()).toBeNull();
    expect(mockNotifService.show).toHaveBeenCalledWith('success', expect.any(String));
  });

  it('notifies when the ComfyUI hand-off fails', async () => {
    mockStore.openInComfy.mockReturnValue(throwError(() => new HttpErrorResponse({})));
    const c = await createComponent();
    c.loadInComfy(makeWorkflow(1));
    expect(mockNotifService.show).toHaveBeenCalledWith(
      'error',
      'Could not hand the workflow to ComfyUI.',
    );
    expect(c.busyWorkflowId()).toBeNull();
  });

  it('exports a graph and notifies', async () => {
    const c = await createComponent();
    c.export(makeWorkflow(2));
    expect(mockStore.exportWorkflow).toHaveBeenCalledWith(2);
    expect(mockNotifService.show).toHaveBeenCalledWith('success', expect.any(String));
  });

  it('notifies when export fails', async () => {
    mockStore.exportWorkflow.mockReturnValue(throwError(() => new HttpErrorResponse({})));
    const c = await createComponent();
    c.export(makeWorkflow(2));
    expect(mockNotifService.show).toHaveBeenCalledWith('error', 'Export failed.');
  });

  it('removes the entry from the list after deletion', async () => {
    mockStore.list.mockReturnValue(of([makeEntry(10), makeEntry(11)]));
    const c = await createComponent();
    c.deleteEntry(makeEntry(10));
    expect(c.entries().map((e) => e.id)).toEqual([11]);
    expect(mockNotifService.show).toHaveBeenCalledWith('success', expect.any(String));
  });

  it('keeps the entry when deletion fails', async () => {
    mockStore.list.mockReturnValue(of([makeEntry(10)]));
    mockStore.deleteEntry.mockReturnValue(throwError(() => new HttpErrorResponse({})));
    const c = await createComponent();
    c.deleteEntry(makeEntry(10));
    expect(c.entries()).toHaveLength(1);
    expect(mockNotifService.show).toHaveBeenCalledWith('error', 'Could not delete the workflow.');
  });

  it('prefers a locally stored image over the remote thumbnail', async () => {
    const c = await createComponent();
    const entry = makeEntry(10, {
      media: [{ id: 0, media_type: 'image', local_path: '/media/hash/0.jpg' }],
    });
    expect(c.thumbUrl(entry)).toContain('%2Fmedia%2Fhash%2F0.jpg');
  });

  it('falls back to the remote thumbnail when there is no local image', async () => {
    const c = await createComponent();
    expect(c.thumbUrl(makeEntry())).toBe('https://img/remote.jpg');
  });

  it('ignores video media when picking the thumbnail', async () => {
    const c = await createComponent();
    const entry = makeEntry(10, {
      media: [{ id: 0, media_type: 'video', local_path: '/media/hash/0.mp4' }],
    });
    expect(c.thumbUrl(entry)).toBe('https://img/remote.jpg');
  });

  it('builds the raw-JSON download url', async () => {
    const c = await createComponent();
    expect(c.fileUrl(makeWorkflow(4))).toBe('/tiny-model-manager/api/workflows/4/file');
  });

  it('toggles image visibility on load and error', async () => {
    const c = await createComponent();
    const img = document.createElement('img');
    c.onImgLoad({ target: img } as unknown as Event);
    expect(img.style.display).toBe('block');
    c.onImgError({ target: img } as unknown as Event);
    expect(img.style.display).toBe('none');
  });

  describe('template', () => {
    it('renders the empty state when nothing is stored', async () => {
      const el = (await render()).nativeElement;
      expect(el.querySelector('.state-box')?.textContent).toContain('No workflows downloaded yet');
      expect(el.querySelector('.card-grid')).toBeNull();
    });

    it('renders the error state with a retry button', async () => {
      mockStore.list.mockReturnValue(
        throwError(() => new HttpErrorResponse({ error: { error: 'db down' } })),
      );
      const el = (await render()).nativeElement;
      expect(el.querySelector('.state-box')?.textContent).toContain('db down');
      expect(el.querySelector('.state-box button')).toBeTruthy();
    });

    it('renders a card per entry with a row per graph', async () => {
      mockStore.list.mockReturnValue(of([makeEntry()]));
      const el = (await render()).nativeElement;
      expect(el.querySelectorAll('.workflow-card')).toHaveLength(1);
      expect(el.querySelector('.card-title')?.textContent).toContain('Cool Pack');
      expect(el.querySelectorAll('.graph-row')).toHaveLength(2);
      expect(el.querySelector('.installed-summary')?.textContent).toContain('2 workflows');
    });

    it('renders the three per-graph actions and the delete trigger', async () => {
      mockStore.list.mockReturnValue(of([makeEntry(10, { items: [makeWorkflow(1)] })]));
      const el = (await render()).nativeElement;
      const actions = el.querySelector('.graph-actions');
      expect(actions.querySelectorAll('button')).toHaveLength(2);
      expect(actions.querySelector('a')?.getAttribute('href')).toBe(
        '/tiny-model-manager/api/workflows/1/file',
      );
      expect(el.querySelector('app-confirm-popover')).toBeTruthy();
      expect(el.querySelector('.source-link')?.getAttribute('href')).toContain('civitai.com');
    });

    it('loads a graph into ComfyUI when its button is clicked', async () => {
      mockStore.list.mockReturnValue(of([makeEntry(10, { items: [makeWorkflow(5)] })]));
      const el = (await render()).nativeElement;
      el.querySelector('.graph-actions button').click();
      expect(mockStore.openInComfy).toHaveBeenCalledWith(5);
    });

    it('omits the thumbnail image when the entry has none', async () => {
      mockStore.list.mockReturnValue(of([makeEntry(10, { thumbnail_url: '', media: [] })]));
      const el = (await render()).nativeElement;
      expect(el.querySelector('.card-media img')).toBeNull();
    });
  });
});
