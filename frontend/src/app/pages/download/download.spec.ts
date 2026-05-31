import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError, EMPTY } from 'rxjs';
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
};

const mockModelService = {
  listModels: vi.fn().mockReturnValue(of({})),
};

const mockNotifService = {
  show: vi.fn(),
};

describe('Download component — F-37 Load More', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockModelService.listModels.mockReturnValue(of({}));
    mockCivitaiService.search.mockReturnValue(
      of({ items: [civitaiModel(1)], metadata: { nextCursor: 'cur1' } }),
    );
    mockHfService.search.mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 }));

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
  });

  async function createFixture() {
    const fixture = TestBed.createComponent(Download);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

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

    it('sets loadMoreError to "No results returned" when items array is empty', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      mockCivitaiService.search.mockReturnValue(of({ items: [], metadata: { nextCursor: '' } }));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBe('No results returned');
      expect(mockNotifService.show).toHaveBeenCalledWith('error', 'No results returned');
    });

    it('does not append items when response is empty', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      c.civitaiResults.set([civitaiModel(1)]);
      mockCivitaiService.search.mockReturnValue(of({ items: [], metadata: { nextCursor: '' } }));

      c.loadMore();
      await fixture.whenStable();

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

    it('sets loadMoreError to "No results returned" when items array is empty', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('huggingface');
      mockHfService.search.mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 }));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBe('No results returned');
      expect(mockNotifService.show).toHaveBeenCalledWith('error', 'No results returned');
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
