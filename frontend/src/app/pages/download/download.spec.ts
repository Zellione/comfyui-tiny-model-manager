import { TestBed } from '@angular/core/testing';
import { ActivatedRoute } from '@angular/router';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { of, EMPTY } from 'rxjs';
import { vi } from 'vitest';
import { Download } from './download';
import { CivitaiService } from '../../services/civitai';
import { HuggingFaceService } from '../../services/huggingface';
import { DownloadService, DownloadTask, DownloadHistoryEntry } from '../../services/download';
import { ModelService } from '../../services/model';
import { NotificationService } from '../../services/notification';
import { KeywordsService } from '../../services/keywords';
import { FilenameKeyword } from '../../utils/filename-detector';

const emptyQueryParams = { get: () => null };

const mockCivitaiService = {
  search: vi.fn().mockReturnValue(of({ items: [], metadata: {} })),
  getVersions: vi.fn().mockReturnValue(EMPTY),
  resolveDirectLink: vi.fn().mockReturnValue(EMPTY),
};

const mockHfService = {
  search: vi.fn().mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 })),
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

const mockNotifService = { show: vi.fn() };

const mockKeywordsService = {
  getKeywords: vi.fn(() => of([] as FilenameKeyword[])),
};

async function createFixture() {
  await TestBed.configureTestingModule({
    imports: [Download],
    providers: [
      { provide: ActivatedRoute, useValue: { snapshot: { queryParamMap: emptyQueryParams } } },
      { provide: CivitaiService, useValue: mockCivitaiService },
      { provide: HuggingFaceService, useValue: mockHfService },
      { provide: DownloadService, useValue: mockDownloadService },
      { provide: ModelService, useValue: mockModelService },
      { provide: NotificationService, useValue: mockNotifService },
      { provide: KeywordsService, useValue: mockKeywordsService },
      provideTranslateServiceForTests(),
    ],
  }).compileComponents();
  const fixture = TestBed.createComponent(Download);
  fixture.detectChanges();
  await fixture.whenStable();
  return fixture;
}

describe('Download — tab shell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDownloadService.activeTasks$ = of([] as DownloadTask[]);
    mockDownloadService.getHistory.mockReturnValue(
      of({ entries: [] as DownloadHistoryEntry[], total: 0 }),
    );
    mockModelService.listModels.mockReturnValue(of({}));
  });

  it('defaults to the active tab', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.activeTab()).toBe('active');
  });

  it('renders the search and paste-link sections on the active tab', async () => {
    const fixture = await createFixture();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('app-download-search')).not.toBeNull();
    expect(el.querySelector('app-paste-link')).not.toBeNull();
    expect(el.querySelector('app-download-queue')).not.toBeNull();
  });

  it('switches to the history tab', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.activeTab.set('history');
    fixture.detectChanges();
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('app-download-history')).not.toBeNull();
    expect(el.querySelector('app-download-search')).toBeNull();
  });
});
