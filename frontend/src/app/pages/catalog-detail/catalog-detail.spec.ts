import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { CatalogDetail } from './catalog-detail';
import { ModelService, CatalogEntryDetail } from '../../services/model';
import { DownloadService } from '../../services/download';
import { NotificationService } from '../../services/notification';

const mockEntry: CatalogEntryDetail = {
  id: 1,
  source_platform: 'civitai',
  source_page_id: '123',
  source_page_url: 'https://civitai.com/models/123',
  display_name: 'Test Model',
  thumbnail_url: '',
  base_model: 'SDXL',
  created_at: '2024-01-01T00:00:00',
  model_type: 'loras',
  is_empty: false,
  installed_files: [],
  repo_files: [
    {
      filename: 'test.safetensors',
      model_type: 'loras',
      size_bytes: 1024,
      download_url: 'https://example.com/test.safetensors',
      source_page_url: '',
      is_downloaded: false,
      added_at: null,
      installed_path: '',
      base_model: '',
    },
  ],
};

const mockModelService = {
  getCatalogEntry: vi.fn(),
  removeCatalogEntry: vi.fn(),
};

const mockDownloadService = {
  startDownload: vi.fn(),
  activeTasks$: of([]),
  completedTasks$: of([]),
};

const mockNotifService = {
  show: vi.fn(),
};

function makeRoute(platform: string, pageId: string) {
  return {
    snapshot: {
      paramMap: { get: (k: string) => (k === 'platform' ? platform : null) },
      queryParamMap: { get: (k: string) => (k === 'pageId' ? pageId : null) },
    },
  };
}

describe('CatalogDetail component', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockModelService.getCatalogEntry.mockReturnValue(of(mockEntry));
  });

  async function createFixture(platform = 'civitai', pageId = '123') {
    await TestBed.configureTestingModule({
      imports: [CatalogDetail],
      providers: [
        provideRouter([{ path: '**', redirectTo: '' }]),
        { provide: ActivatedRoute, useValue: makeRoute(platform, pageId) },
        { provide: ModelService, useValue: mockModelService },
        { provide: DownloadService, useValue: mockDownloadService },
        { provide: NotificationService, useValue: mockNotifService },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(CatalogDetail);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  afterEach(() => TestBed.resetTestingModule());

  it('creates successfully', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('loads the catalog entry on init', async () => {
    const fixture = await createFixture();
    expect(mockModelService.getCatalogEntry).toHaveBeenCalledWith('civitai', '123');
    expect(fixture.componentInstance.entry()?.display_name).toBe('Test Model');
  });

  it('sets loading to false after successful load', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.loading()).toBe(false);
  });

  it('sets error signal on load failure', async () => {
    mockModelService.getCatalogEntry.mockReturnValue(throwError(() => new Error('not found')));
    const fixture = await createFixture();
    expect(fixture.componentInstance.error()).toBe('not found');
  });

  it('computes downloadedFiles correctly', async () => {
    mockModelService.getCatalogEntry.mockReturnValue(
      of({
        ...mockEntry,
        repo_files: [
          { ...mockEntry.repo_files[0], is_downloaded: true },
          { ...mockEntry.repo_files[0], filename: 'b.safetensors', is_downloaded: false },
        ],
      }),
    );
    const fixture = await createFixture();
    expect(fixture.componentInstance.downloadedFiles().length).toBe(1);
    expect(fixture.componentInstance.notDownloadedFiles().length).toBe(1);
  });

  it('sourceName is correct for civitai', async () => {
    const fixture = await createFixture('civitai', '123');
    expect(fixture.componentInstance.sourceName()).toBe('CivitAI');
  });

  it('sourceName is correct for huggingface', async () => {
    const fixture = await createFixture('huggingface', 'stabilityai/sdxl');
    expect(fixture.componentInstance.sourceName()).toBe('HuggingFace');
  });

  it('showRemoveConfirm starts false', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.showRemoveConfirm()).toBe(false);
  });

  it('removeFromCatalog calls service', async () => {
    mockModelService.removeCatalogEntry.mockReturnValue(of(undefined));
    const fixture = await createFixture();
    fixture.componentInstance.removeFromCatalog();
    expect(mockModelService.removeCatalogEntry).toHaveBeenCalledWith('civitai', '123');
  });
});
