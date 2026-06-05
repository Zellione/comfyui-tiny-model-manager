import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError, EMPTY, Subject } from 'rxjs';
import { vi } from 'vitest';
import { HttpErrorResponse } from '@angular/common/http';
import { Download } from './download';
import { CivitaiService } from '../../services/civitai';
import { HuggingFaceService } from '../../services/huggingface';
import { DownloadService, DownloadTask } from '../../services/download';
import { ModelService } from '../../services/model';
import { NotificationService } from '../../services/notification';

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
};

const mockModelService = {
  listModels: vi.fn().mockReturnValue(of({})),
};

const mockNotifService = {
  show: vi.fn(),
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
});
