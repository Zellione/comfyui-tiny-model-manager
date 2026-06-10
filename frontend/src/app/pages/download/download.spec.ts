import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError, EMPTY, Subject } from 'rxjs';
import { vi } from 'vitest';
import { HttpErrorResponse } from '@angular/common/http';
import { Download } from './download';
import { CivitaiService, CivitaiFile, CivitaiVersion } from '../../services/civitai';
import { HuggingFaceService, HfModel } from '../../services/huggingface';
import { DownloadService, DownloadTask, DownloadHistoryEntry } from '../../services/download';
import { ModelService } from '../../services/model';
import { NotificationService } from '../../services/notification';
import { KeywordsService } from '../../services/keywords';
import { FilenameKeyword } from '../../utils/filename-detector';

const civitaiModel = (id: number) => ({
  id,
  name: `Model ${id}`,
  type: 'LORA',
  description: '',
  tags: [],
  modelVersions: [],
  creator: { username: '' },
  stats: { downloadCount: 0, thumbsUpCount: 0, thumbsDownCount: 0 },
});

const mockCivitaiService = {
  search: vi.fn(),
  getVersions: vi.fn().mockReturnValue(EMPTY),
  resolveDirectLink: vi.fn().mockReturnValue(EMPTY),
};

const mockHfService = {
  search: vi.fn(),
  getFiles: vi.fn().mockReturnValue(EMPTY),
  getReadme: vi.fn().mockReturnValue(EMPTY),
  resolveDirectLink: vi.fn().mockReturnValue(EMPTY),
};

const mockDownloadService = {
  activeTasks$: of([] as DownloadTask[]),
  completedTasks$: EMPTY,
  startDownload: vi.fn().mockReturnValue(of({})),
  cancelDownload: vi.fn().mockReturnValue(of(void 0)),
  getHistory: vi.fn().mockReturnValue(of({ entries: [] as DownloadHistoryEntry[], total: 0 })),
  redownload: vi.fn().mockReturnValue(of({ task_id: 'task-new' })),
};

const mockModelService = {
  listModels: vi.fn().mockReturnValue(of({})),
};

const mockNotifService = {
  show: vi.fn(),
};

const mockKeywordsService = {
  getKeywords: vi.fn(() => of([] as FilenameKeyword[])),
};

async function configureTestBed() {
  await TestBed.configureTestingModule({
    imports: [Download],
    providers: [
      provideRouter([]),
      { provide: CivitaiService, useValue: mockCivitaiService },
      { provide: HuggingFaceService, useValue: mockHfService },
      { provide: DownloadService, useValue: mockDownloadService },
      { provide: ModelService, useValue: mockModelService },
      { provide: NotificationService, useValue: mockNotifService },
      { provide: KeywordsService, useValue: mockKeywordsService },
    ],
  }).compileComponents();
}

async function createFixture() {
  const fixture = TestBed.createComponent(Download);
  fixture.detectChanges();
  await fixture.whenStable();
  return fixture;
}

describe('Download component — F-37 Load More', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockModelService.listModels.mockReturnValue(of({}));
    mockCivitaiService.search.mockReturnValue(
      of({ items: [civitaiModel(1)], metadata: { nextCursor: 'cur1' } }),
    );
    mockHfService.search.mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 }));
    await configureTestBed();
  });

  describe('initial signal state', () => {
    it('loadMoreError starts empty', async () => {
      const fixture = await createFixture();
      expect(fixture.componentInstance.loadMoreError()).toBe('');
    });

    it('activeHasMore reflects civitaiHasMore when platform is civitai', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      c.civitaiHasMore.set(true);
      c.hfHasMore.set(false);
      expect(c.activeHasMore()).toBe(true);
    });

    it('activeHasMore reflects hfHasMore when platform is huggingface', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('huggingface');
      c.civitaiHasMore.set(false);
      c.hfHasMore.set(true);
      expect(c.activeHasMore()).toBe(true);
    });
  });

  describe('search() resets error', () => {
    it('clears loadMoreError when a new search is triggered', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.loadMoreError.set('previous error');

      c.search();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBe('');
    });

    it('clears searchError when a new search is triggered', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.searchError.set('previous search error');

      c.search();
      await fixture.whenStable();

      expect(c.searchError()).toBe('');
    });
  });

  describe('search() error handling', () => {
    it('sets searchError on CivitAI HTTP error', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      const err = new HttpErrorResponse({ error: { error: 'Rate limited' }, status: 429 });
      mockCivitaiService.search.mockReturnValue(throwError(() => err));

      c.search();
      await fixture.whenStable();

      expect(c.searchError()).toBe('Rate limited');
      expect(c.searching()).toBe(false);
    });

    it('sets searchError on HuggingFace HTTP error', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('huggingface');
      const err = new HttpErrorResponse({ error: { error: 'Service unavailable' }, status: 503 });
      mockHfService.search.mockReturnValue(throwError(() => err));

      c.search();
      await fixture.whenStable();

      expect(c.searchError()).toBe('Service unavailable');
      expect(c.searching()).toBe(false);
    });

    it('falls back to err.message when error body has no error field', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      const err = new HttpErrorResponse({ error: null, status: 0, statusText: 'Unknown Error' });
      mockCivitaiService.search.mockReturnValue(throwError(() => err));

      c.search();
      await fixture.whenStable();

      expect(c.searchError()).toBeTruthy();
      expect(c.searching()).toBe(false);
    });
  });

  describe('loadMore() — CivitAI', () => {
    it('appends items and updates pagination on success', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      c.civitaiResults.set([civitaiModel(1)]);
      mockCivitaiService.search.mockReturnValue(
        of({ items: [civitaiModel(2)], metadata: { nextCursor: 'cur2' } }),
      );

      c.loadMore();
      await fixture.whenStable();

      expect(c.civitaiResults()).toHaveLength(2);
      expect(c.civitaiCursor()).toBe('cur2');
      expect(c.civitaiHasMore()).toBe(true);
      expect(c.loadMoreError()).toBe('');
    });

    it('sets loadMoreError and shows error toast on HTTP error', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      const err = new HttpErrorResponse({ error: { error: 'Rate limited' }, status: 429 });
      mockCivitaiService.search.mockReturnValue(throwError(() => err));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBe('Rate limited');
      expect(mockNotifService.show).toHaveBeenCalledWith('error', 'Rate limited');
    });

    it('falls back to err.message when error body has no error field', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      const err = new HttpErrorResponse({ error: null, status: 500, statusText: 'Server Error' });
      mockCivitaiService.search.mockReturnValue(throwError(() => err));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBeTruthy();
      expect(mockNotifService.show).toHaveBeenCalledWith('error', expect.any(String));
    });

    it('sets loadMoreError to "No results returned" when items are empty (first attempt)', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      mockCivitaiService.search.mockReturnValue(of({ items: [], metadata: { nextCursor: '' } }));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBe('No results returned');
      expect(mockNotifService.show).toHaveBeenCalledWith('error', 'No results returned');
    });

    it('treats empty items as end of results on retry (wasError=true)', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      c.loadMoreError.set('previous error');
      c.civitaiResults.set([civitaiModel(1)]);
      mockCivitaiService.search.mockReturnValue(of({ items: [], metadata: { nextCursor: '' } }));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBe('');
      expect(c.civitaiHasMore()).toBe(false);
      expect(mockNotifService.show).not.toHaveBeenCalled();
      expect(c.civitaiResults()).toHaveLength(1);
    });

    it('sets loadingMore to false after error', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      mockCivitaiService.search.mockReturnValue(throwError(() => new Error('fail')));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadingMore()).toBe(false);
    });

    it('clears previous loadMoreError when retrying', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      c.loadMoreError.set('old error');
      mockCivitaiService.search.mockReturnValue(
        of({ items: [civitaiModel(3)], metadata: { nextCursor: '' } }),
      );

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBe('');
    });
  });

  describe('loadMore() — HuggingFace', () => {
    it('appends items and updates pagination on success', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('huggingface');
      const existingModel = { id: 'a/m1', modelId: 'a/m1', downloads: 0, tags: [] };
      c.hfResults.set([existingModel]);
      const newModel = { id: 'a/m2', modelId: 'a/m2', downloads: 0, tags: [] };
      mockHfService.search.mockReturnValue(of({ items: [newModel], hasMore: false, nextPage: 2 }));

      c.loadMore();
      await fixture.whenStable();

      expect(c.hfResults()).toHaveLength(2);
      expect(c.hfPage()).toBe(2);
      expect(c.hfHasMore()).toBe(false);
      expect(c.loadMoreError()).toBe('');
    });

    it('sets loadMoreError and shows error toast on HTTP error', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('huggingface');
      const err = new HttpErrorResponse({ error: { error: 'Model not found' }, status: 404 });
      mockHfService.search.mockReturnValue(throwError(() => err));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBe('Model not found');
      expect(mockNotifService.show).toHaveBeenCalledWith('error', 'Model not found');
    });

    it('sets loadMoreError to "No results returned" when items are empty (first attempt)', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('huggingface');
      mockHfService.search.mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 }));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBe('No results returned');
      expect(mockNotifService.show).toHaveBeenCalledWith('error', 'No results returned');
    });

    it('treats empty items as end of results on retry (wasError=true)', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('huggingface');
      c.loadMoreError.set('previous error');
      mockHfService.search.mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 }));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBe('');
      expect(c.hfHasMore()).toBe(false);
      expect(mockNotifService.show).not.toHaveBeenCalled();
    });

    it('sets loadingMore to false after error', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('huggingface');
      mockHfService.search.mockReturnValue(throwError(() => new Error('fail')));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadingMore()).toBe(false);
    });
  });
});

describe('Download component — F-43 Cancel Download', () => {
  const activeTask = (): DownloadTask => ({
    id: 'task-1',
    url: 'https://example.com/m.safetensors',
    model_type: 'loras',
    filename: 'm.safetensors',
    platform: 'civitai',
    source_id: '123',
    status: 'downloading',
    progress: 50,
    downloaded_bytes: 512,
    total_bytes: 1024,
    error: null,
    history_id: null,
  });

  beforeEach(async () => {
    vi.clearAllMocks();
    mockDownloadService.activeTasks$ = of([activeTask()]);
    mockDownloadService.cancelDownload.mockReturnValue(of(void 0));
    mockModelService.listModels.mockReturnValue(of({}));
    mockCivitaiService.search.mockReturnValue(of({ items: [], metadata: {} }));
    mockHfService.search.mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 }));
    await configureTestBed();
  });

  it('onCancelTask calls cancelDownload with the task id', async () => {
    const fixture = await createFixture();
    fixture.componentInstance.onCancelTask('task-1');
    expect(mockDownloadService.cancelDownload).toHaveBeenCalledWith('task-1');
  });

  it('adds task to cancelledIds on success', async () => {
    const fixture = await createFixture();
    fixture.componentInstance.onCancelTask('task-1');
    expect(fixture.componentInstance.cancelledIds().has('task-1')).toBe(true);
  });

  it('adds task to cancelledIds on 404 (already done)', async () => {
    mockDownloadService.cancelDownload.mockReturnValue(
      throwError(() => new HttpErrorResponse({ status: 404 })),
    );
    const fixture = await createFixture();
    fixture.componentInstance.onCancelTask('task-1');
    expect(fixture.componentInstance.cancelledIds().has('task-1')).toBe(true);
  });

  it('tracks in-flight cancellation in cancellingIds', async () => {
    const subject = new Subject<void>();
    mockDownloadService.cancelDownload.mockReturnValue(subject.asObservable());
    const fixture = await createFixture();

    fixture.componentInstance.onCancelTask('task-1');
    expect(fixture.componentInstance.cancellingIds().has('task-1')).toBe(true);

    subject.next();
    subject.complete();
    expect(fixture.componentInstance.cancellingIds().has('task-1')).toBe(false);
  });

  it('displayTasks excludes cancelled ids', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    expect(c.displayTasks().length).toBe(1);
    c.onCancelTask('task-1');
    expect(c.displayTasks().length).toBe(0);
  });

  it('onCancelAll cancels every display task', async () => {
    const tasks: DownloadTask[] = [
      { ...activeTask(), id: 'task-1', filename: 'a.safetensors' },
      { ...activeTask(), id: 'task-2', filename: 'b.safetensors', status: 'queued' },
    ];
    mockDownloadService.activeTasks$ = of(tasks);
    const fixture = await createFixture();
    fixture.componentInstance.onCancelAll();
    expect(mockDownloadService.cancelDownload).toHaveBeenCalledWith('task-1');
    expect(mockDownloadService.cancelDownload).toHaveBeenCalledWith('task-2');
  });

  it('hasCancellableTasks is false when all tasks are done', async () => {
    mockDownloadService.activeTasks$ = of([{ ...activeTask(), status: 'done' }]);
    const fixture = await createFixture();
    expect(fixture.componentInstance.hasCancellableTasks()).toBe(false);
  });

  it('hasCancellableTasks is true when at least one task is downloading', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.hasCancellableTasks()).toBe(true);
  });

  it('hasCancellableTasks is false when all tasks are errors', async () => {
    mockDownloadService.activeTasks$ = of([{ ...activeTask(), status: 'error' }]);
    const fixture = await createFixture();
    expect(fixture.componentInstance.hasCancellableTasks()).toBe(false);
  });
});

const historyEntry = (id: number): DownloadHistoryEntry => ({
  id,
  model_name: `model_${id}.safetensors`,
  source: 'civitai',
  model_id: '',
  version_id: String(id),
  file_url: `https://example.com/${id}.safetensors`,
  dest_path: `model_${id}.safetensors`,
  model_type: 'checkpoints',
  status: 'done',
  created_at: '2024-01-01T00:00:00',
  updated_at: '2024-01-01T00:00:00',
});

describe('Download component — F-47 History tab', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockDownloadService.activeTasks$ = of([] as DownloadTask[]);
    mockDownloadService.getHistory.mockReturnValue(
      of({ entries: [] as DownloadHistoryEntry[], total: 0 }),
    );
    mockDownloadService.redownload.mockReturnValue(of({ task_id: 'task-new' }));
    mockModelService.listModels.mockReturnValue(of({}));
    mockCivitaiService.search.mockReturnValue(of({ items: [], metadata: {} }));
    mockHfService.search.mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 }));
    await configureTestBed();
  });

  it('historyHasMore is true when entries count is less than total', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.historyEntries.set([historyEntry(1), historyEntry(2)]);
    c.historyTotal.set(5);
    expect(c.historyHasMore()).toBe(true);
  });

  it('historyHasMore is false when entries count equals total', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.historyEntries.set([historyEntry(1)]);
    c.historyTotal.set(1);
    expect(c.historyHasMore()).toBe(false);
  });

  it('historyTaskMap maps tasks by history_id', async () => {
    const task: DownloadTask = {
      id: 'task-h1',
      url: 'https://example.com/m.safetensors',
      model_type: 'checkpoints',
      filename: 'm.safetensors',
      platform: 'civitai',
      source_id: '1',
      status: 'downloading',
      progress: 50,
      downloaded_bytes: 512,
      total_bytes: 1024,
      error: null,
      history_id: 42,
    };
    mockDownloadService.activeTasks$ = of([task]);
    await configureTestBed();
    const fixture = await createFixture();
    expect(fixture.componentInstance.historyTaskMap().get(42)?.id).toBe('task-h1');
  });

  it('historyTaskMap excludes tasks without history_id', async () => {
    const task: DownloadTask = {
      id: 'task-h2',
      url: 'https://example.com/m.safetensors',
      model_type: 'checkpoints',
      filename: 'm.safetensors',
      platform: 'civitai',
      source_id: '1',
      status: 'downloading',
      progress: 50,
      downloaded_bytes: 512,
      total_bytes: 1024,
      error: null,
      history_id: null,
    };
    mockDownloadService.activeTasks$ = of([task]);
    await configureTestBed();
    const fixture = await createFixture();
    expect(fixture.componentInstance.historyTaskMap().size).toBe(0);
  });

  it('loadHistory(true) resets entries and populates from service', async () => {
    const entries = [historyEntry(1), historyEntry(2)];
    mockDownloadService.getHistory.mockReturnValue(of({ entries, total: 2 }));
    const fixture = await createFixture();
    const c = fixture.componentInstance;

    c.loadHistory(true);
    await fixture.whenStable();

    expect(c.historyEntries()).toHaveLength(2);
    expect(c.historyTotal()).toBe(2);
    expect(c.historyLoading()).toBe(false);
  });

  it('loadHistory(true) resets page to 1', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.historyPage.set(3);

    c.loadHistory(true);
    await fixture.whenStable();

    expect(c.historyPage()).toBe(1);
  });

  it('loadHistory(false) appends entries to existing list', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.historyEntries.set([historyEntry(1)]);
    mockDownloadService.getHistory.mockReturnValue(of({ entries: [historyEntry(2)], total: 2 }));

    c.loadHistory(false);
    await fixture.whenStable();

    expect(c.historyEntries()).toHaveLength(2);
  });

  it('loadHistory error sets historyLoadMoreError and clears loading', async () => {
    mockDownloadService.getHistory.mockReturnValue(throwError(() => new Error('Network error')));
    const fixture = await createFixture();
    const c = fixture.componentInstance;

    c.loadHistory(true);
    await fixture.whenStable();

    expect(c.historyLoadMoreError()).toBe('Failed to load history');
    expect(c.historyLoading()).toBe(false);
  });

  it('historyLoadMore increments page and appends entries', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.historyPage.set(1);
    c.historyEntries.set([historyEntry(1)]);
    mockDownloadService.getHistory.mockReturnValue(of({ entries: [historyEntry(2)], total: 2 }));

    c.historyLoadMore();
    await fixture.whenStable();

    expect(c.historyPage()).toBe(2);
    expect(c.historyEntries()).toHaveLength(2);
  });

  it('redownload adds id to historyRedownloadingIds during request then removes on success', async () => {
    const subject = new Subject<{ task_id: string }>();
    mockDownloadService.redownload.mockReturnValue(subject.asObservable());
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    const entry = historyEntry(1);

    c.redownload(entry);
    expect(c.historyRedownloadingIds().has(1)).toBe(true);

    subject.next({ task_id: 'task-new' });
    subject.complete();
    expect(c.historyRedownloadingIds().has(1)).toBe(false);
  });

  it('redownload success switches activeTab to active', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.activeTab.set('active');
    const entry = historyEntry(1);

    c.redownload(entry);
    await fixture.whenStable();

    expect(c.activeTab()).toBe('active');
  });

  it('redownload success shows success notification', async () => {
    const fixture = await createFixture();
    const entry = historyEntry(1);

    fixture.componentInstance.redownload(entry);
    await fixture.whenStable();

    expect(mockNotifService.show).toHaveBeenCalledWith(
      'success',
      expect.stringContaining(entry.model_name),
    );
  });

  it('redownload error shows error notification', async () => {
    mockDownloadService.redownload.mockReturnValue(throwError(() => new Error('failed')));
    const fixture = await createFixture();
    const entry = historyEntry(1);

    fixture.componentInstance.redownload(entry);
    await fixture.whenStable();

    expect(mockNotifService.show).toHaveBeenCalledWith(
      'error',
      expect.stringContaining(entry.model_name),
    );
  });

  it('redownload error clears historyRedownloadingIds', async () => {
    mockDownloadService.redownload.mockReturnValue(throwError(() => new Error('failed')));
    const fixture = await createFixture();
    const entry = historyEntry(1);

    fixture.componentInstance.redownload(entry);
    await fixture.whenStable();

    expect(fixture.componentInstance.historyRedownloadingIds().has(1)).toBe(false);
  });

  it('historyStatusLabel returns human-readable labels', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    expect(c.historyStatusLabel('done')).toBe('Done');
    expect(c.historyStatusLabel('error')).toBe('Error');
    expect(c.historyStatusLabel('cancelled')).toBe('Cancelled');
    expect(c.historyStatusLabel('downloading')).toBe('Downloading');
    expect(c.historyStatusLabel('deleted')).toBe('Deleted');
  });

  it('historyStatusLabel returns raw status for unknown values', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    expect(c.historyStatusLabel('unknown' as DownloadHistoryEntry['status'])).toBe('unknown');
  });

  it('canRedownload returns true for error, cancelled, and deleted', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    expect(c.canRedownload('error')).toBe(true);
    expect(c.canRedownload('cancelled')).toBe(true);
    expect(c.canRedownload('deleted')).toBe(true);
  });

  it('canRedownload returns false for done and downloading', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    expect(c.canRedownload('done')).toBe(false);
    expect(c.canRedownload('downloading')).toBe(false);
  });
});

describe('Download component — tag methods', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockDownloadService.activeTasks$ = of([] as DownloadTask[]);
    mockDownloadService.getHistory.mockReturnValue(
      of({ entries: [] as DownloadHistoryEntry[], total: 0 }),
    );
    mockModelService.listModels.mockReturnValue(of({}));
    mockCivitaiService.search.mockReturnValue(of({ items: [], metadata: {} }));
    mockHfService.search.mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 }));
    await configureTestBed();
  });

  it('addTag appends a trimmed tag to tagFilter and clears tagInput', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.tagInput.set('anime');
    c.addTag('  anime  ');
    expect(c.tagFilter()).toContain('anime');
    expect(c.tagInput()).toBe('');
  });

  it('addTag ignores duplicate tags', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.addTag('lora');
    c.addTag('lora');
    expect(c.tagFilter()).toHaveLength(1);
  });

  it('addTag ignores blank strings', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.addTag('   ');
    expect(c.tagFilter()).toHaveLength(0);
  });

  it('addTagFromInput adds the current tagInput value', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.tagInput.set('  lora  ');
    c.addTagFromInput();
    expect(c.tagFilter()).toContain('lora');
    expect(c.tagInput()).toBe('');
  });

  it('addTagFromInput does nothing when tagInput is blank', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.tagInput.set('');
    c.addTagFromInput();
    expect(c.tagFilter()).toHaveLength(0);
  });

  it('removeTag removes the specified tag and keeps others', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.tagFilter.set(['anime', 'lora']);
    c.removeTag('anime');
    expect(c.tagFilter()).not.toContain('anime');
    expect(c.tagFilter()).toContain('lora');
  });
});

describe('Download component — fileStatus', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockDownloadService.activeTasks$ = of([] as DownloadTask[]);
    mockDownloadService.getHistory.mockReturnValue(
      of({ entries: [] as DownloadHistoryEntry[], total: 0 }),
    );
    mockModelService.listModels.mockReturnValue(of({}));
    mockCivitaiService.search.mockReturnValue(of({ items: [], metadata: {} }));
    mockHfService.search.mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 }));
    await configureTestBed();
  });

  it('returns idle for an unknown filename', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.fileStatus('unknown.safetensors')).toBe('idle');
  });

  it('returns installed when filename is in installedFilenames', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.installedFilenames.set(new Set(['model.safetensors']));
    expect(c.fileStatus('model.safetensors')).toBe('installed');
  });

  it('returns downloading for a task with downloading status', async () => {
    const task: DownloadTask = {
      id: 'task-fs1',
      url: 'https://example.com/m.safetensors',
      model_type: 'checkpoints',
      filename: 'm.safetensors',
      platform: 'civitai',
      source_id: '1',
      status: 'downloading',
      progress: 50,
      downloaded_bytes: 512,
      total_bytes: 1024,
      error: null,
      history_id: null,
    };
    mockDownloadService.activeTasks$ = of([task]);
    await configureTestBed();
    const fixture = await createFixture();
    expect(fixture.componentInstance.fileStatus('m.safetensors')).toBe('downloading');
  });

  it('returns error for a task with error status', async () => {
    const task: DownloadTask = {
      id: 'task-fs2',
      url: 'https://example.com/m.safetensors',
      model_type: 'checkpoints',
      filename: 'm.safetensors',
      platform: 'civitai',
      source_id: '1',
      status: 'error',
      progress: 0,
      downloaded_bytes: 0,
      total_bytes: 0,
      error: 'Network error',
      history_id: null,
    };
    mockDownloadService.activeTasks$ = of([task]);
    await configureTestBed();
    const fixture = await createFixture();
    expect(fixture.componentInstance.fileStatus('m.safetensors')).toBe('error');
  });

  it('returns installed for a task with done status', async () => {
    const task: DownloadTask = {
      id: 'task-fs3',
      url: 'https://example.com/m.safetensors',
      model_type: 'checkpoints',
      filename: 'm.safetensors',
      platform: 'civitai',
      source_id: '1',
      status: 'done',
      progress: 100,
      downloaded_bytes: 1024,
      total_bytes: 1024,
      error: null,
      history_id: null,
    };
    mockDownloadService.activeTasks$ = of([task]);
    await configureTestBed();
    const fixture = await createFixture();
    expect(fixture.componentInstance.fileStatus('m.safetensors')).toBe('installed');
  });

  it('strips subfolder prefix before matching', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.installedFilenames.set(new Set(['model.safetensors']));
    expect(c.fileStatus('split_files/model.safetensors')).toBe('installed');
  });
});

describe('Download component — F-80 HuggingFace model selection', () => {
  const hfModel = (): HfModel => ({
    id: 'user/repo',
    modelId: 'user/repo',
    downloads: 0,
    tags: [],
    description: 'desc',
  });

  beforeEach(async () => {
    vi.clearAllMocks();
    mockModelService.listModels.mockReturnValue(of({}));
    mockCivitaiService.search.mockReturnValue(of({ items: [], metadata: {} }));
    mockHfService.search.mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 }));
    mockHfService.getFiles.mockReturnValue(EMPTY);
    await configureTestBed();
  });

  it('selectHf resets galleryIndex to 0', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.galleryIndex.set(3);
    c.selectHf(hfModel());
    expect(c.galleryIndex()).toBe(0);
  });
});

const mockCivitaiFile: CivitaiFile = {
  id: 101,
  name: 'model.safetensors',
  type: 'Model',
  sizeKB: 1024,
  downloadUrl: 'https://example.com/model.safetensors',
  primary: true,
  metadata: { format: 'SafeTensor', size: 'full', fp: 'fp16' },
};

describe('Download component — F-82 base model signals', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockKeywordsService.getKeywords.mockReturnValue(of([]));
    mockModelService.listModels.mockReturnValue(of({}));
    mockCivitaiService.search.mockReturnValue(of({ items: [], metadata: {} }));
    mockHfService.search.mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 }));
    mockDownloadService.activeTasks$ = of([]);
    await configureTestBed();
  });

  it('hfRowBaseModel returns empty string for unknown key', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.hfRowBaseModel('unknown.safetensors')).toBe('');
  });

  it('setHfRowBaseModel stores a value retrievable by hfRowBaseModel', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.setHfRowBaseModel('model.safetensors', 'SDXL 1.0');
    expect(c.hfRowBaseModel('model.safetensors')).toBe('SDXL 1.0');
  });

  it('linkHfRowBaseModel returns empty string for unknown key', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.linkHfRowBaseModel('unknown.safetensors')).toBe('');
  });

  it('setLinkHfRowBaseModel stores a value retrievable by linkHfRowBaseModel', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.setLinkHfRowBaseModel('model.safetensors', 'Flux.1 D');
    expect(c.linkHfRowBaseModel('model.safetensors')).toBe('Flux.1 D');
  });

  it('civitaiFileBaseModel returns empty string for unknown key', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.civitaiFileBaseModel(1, mockCivitaiFile)).toBe('');
  });

  it('setCivitaiFileBaseModel stores a value retrievable by civitaiFileBaseModel', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.setCivitaiFileBaseModel(1, mockCivitaiFile, 'Pony');
    expect(c.civitaiFileBaseModel(1, mockCivitaiFile)).toBe('Pony');
  });

  it('linkCivitaiFileBaseModel returns empty string for unknown key', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.linkCivitaiFileBaseModel(1, mockCivitaiFile)).toBe('');
  });

  it('setLinkCivitaiFileBaseModel stores a value retrievable by linkCivitaiFileBaseModel', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.setLinkCivitaiFileBaseModel(1, mockCivitaiFile, 'SD 1.5');
    expect(c.linkCivitaiFileBaseModel(1, mockCivitaiFile)).toBe('SD 1.5');
  });
});

describe('Download component — F-82 applyLinkResolution', () => {
  const sdxlKeyword = {
    id: 1,
    keyword: 'sdxl',
    base_model: 'SDXL 1.0',
    model_type: null,
    sort_order: 10,
  };
  const loraKeyword = {
    id: 2,
    keyword: 'lora',
    base_model: null,
    model_type: 'loras',
    sort_order: 20,
  };

  beforeEach(async () => {
    vi.clearAllMocks();
    mockKeywordsService.getKeywords.mockReturnValue(of([sdxlKeyword, loraKeyword]));
    mockModelService.listModels.mockReturnValue(of({}));
    mockCivitaiService.search.mockReturnValue(of({ items: [], metadata: {} }));
    mockHfService.search.mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 }));
    mockDownloadService.activeTasks$ = of([]);
    await configureTestBed();
  });

  it('hf-resolve: sets linkBaseModel and linkImages from resolved data', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.linkResolving.set(true);
    (c as any).applyLinkResolution({
      tag: 'hf-resolve',
      filename: 'sdxl_lora.safetensors',
      image_urls: ['https://example.com/img.jpg'],
    });
    expect(c.linkBaseModel()).toBe('SDXL 1.0');
    expect(c.linkImages()).toEqual(['https://example.com/img.jpg']);
    expect(c.linkResolving()).toBe(false);
  });

  it('hf-resolve: sets linkModelType when keyword provides model_type', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    (c as any).applyLinkResolution({ tag: 'hf-resolve', filename: 'sdxl_lora.safetensors' });
    expect(c.linkModelType()).toBe('loras');
  });

  it('hf-resolve: does not change linkModelType when no model_type keyword matches', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.linkModelType.set('vae');
    (c as any).applyLinkResolution({ tag: 'hf-resolve', filename: 'sdxl_checkpoint.safetensors' });
    expect(c.linkModelType()).toBe('vae');
    expect(c.linkBaseModel()).toBe('SDXL 1.0');
  });

  it('civitai-download: sets linkResolved, linkModelType, linkImages, and linkBaseModel', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.linkResolving.set(true);
    const result = {
      tag: 'civitai-download' as const,
      filename: 'sdxl_model.safetensors',
      model_type: 'checkpoints',
      size_kb: 1024,
      image_urls: ['https://example.com/img1.jpg'],
    };
    (c as any).applyLinkResolution(result);
    expect(c.linkBaseModel()).toBe('SDXL 1.0');
    expect(c.linkModelType()).toBe('checkpoints');
    expect(c.linkImages()).toEqual(['https://example.com/img1.jpg']);
    expect(c.linkResolved()).toBe(result);
    expect(c.linkResolving()).toBe(false);
  });

  it('hf-repo: populates linkHfFiles and sets base models for matching filenames', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.linkResolving.set(true);
    const files = [
      { filename: 'sdxl_model.safetensors', size: 1024, url: 'https://example.com/a.safetensors' },
      { filename: 'plain_model.safetensors', size: 512, url: 'https://example.com/b.safetensors' },
    ];
    (c as any).applyLinkResolution({ tag: 'hf-repo', files });
    expect(c.linkHfFiles()).toEqual(files);
    expect(c.linkHfRowBaseModels()['sdxl_model.safetensors']).toBe('SDXL 1.0');
    expect(c.linkHfRowBaseModels()['plain_model.safetensors']).toBeUndefined();
    expect(c.linkResolving()).toBe(false);
  });

  it('hf-repo: sets linkHfRowTypes for matching model_type keywords', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    (c as any).applyLinkResolution({
      tag: 'hf-repo',
      files: [
        { filename: 'my_lora.safetensors', size: 512, url: 'https://example.com/c.safetensors' },
      ],
    });
    expect(c.linkHfRowTypes()['my_lora.safetensors']).toBe('loras');
  });

  it('civitai-model: sets linkVersions and detects base model from filename when version lacks one', async () => {
    const versions: CivitaiVersion[] = [
      {
        id: 10,
        name: 'v1',
        baseModel: '',
        downloadUrl: 'https://example.com',
        trainedWords: [],
        images: [],
        files: [
          {
            id: 200,
            name: 'sdxl_checkpoint.safetensors',
            type: 'Model',
            sizeKB: 2048,
            downloadUrl: 'https://example.com/d.safetensors',
            primary: true,
            metadata: { format: 'SafeTensor', size: 'full', fp: 'fp16' },
          },
        ],
      },
    ];
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.linkResolving.set(true);
    (c as any).applyLinkResolution({ tag: 'civitai-model', versions, model_type: 'checkpoints' });
    expect(c.linkVersions()).toEqual(versions);
    expect(c.linkModelType()).toBe('checkpoints');
    expect(c.linkCivitaiFileBaseModels()['10_200']).toBe('SDXL 1.0');
    expect(c.linkResolving()).toBe(false);
  });

  it('civitai-model: uses version.baseModel when set, ignoring filename detection', async () => {
    const versions: CivitaiVersion[] = [
      {
        id: 11,
        name: 'v2',
        baseModel: 'Pony',
        downloadUrl: 'https://example.com',
        trainedWords: [],
        images: [],
        files: [
          {
            id: 201,
            name: 'sdxl_checkpoint.safetensors',
            type: 'Model',
            sizeKB: 2048,
            downloadUrl: 'https://example.com/e.safetensors',
            primary: true,
            metadata: { format: 'SafeTensor', size: 'full', fp: 'fp16' },
          },
        ],
      },
    ];
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    (c as any).applyLinkResolution({ tag: 'civitai-model', versions });
    expect(c.linkCivitaiFileBaseModels()['11_201']).toBe('Pony');
  });

  it('null result: sets linkResolving to false without touching other state', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.linkResolving.set(true);
    c.linkBaseModel.set('existing');
    (c as any).applyLinkResolution(null);
    expect(c.linkResolving()).toBe(false);
    expect(c.linkBaseModel()).toBe('existing');
  });
});
