import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { CatalogDetail } from './catalog-detail';
import { ModelService, CatalogEntryDetail, ModelMeta, InstalledFile } from '../../services/model';
import { DownloadService } from '../../services/download';
import { WorkflowService } from '../../services/workflow';
import { NotificationService } from '../../services/notification';

const mockInstalledFile: InstalledFile = {
  filename: 'test.safetensors',
  model_type: 'loras',
  size_bytes: 1024,
  modified_at: 0,
};

const mockMeta: ModelMeta = {
  description: 'A test model',
  trigger_words: ['word1'],
  tags: ['portrait'],
  media: [],
  base_model: 'SDXL 1.0',
  source_platform: 'civitai',
  source_url: 'https://civitai.com/models/123',
  size_bytes: 1024,
};

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
  getMetadata: vi.fn(),
  updateMetadataWithPath: vi.fn(),
  refetchMetadata: vi.fn(),
  deleteModel: vi.fn(),
};

const mockDownloadService = {
  startDownload: vi.fn(),
  activeTasks$: of([]),
  completedTasks$: of([]),
};

const mockWorkflowService = {
  addToWorkflow: vi.fn(),
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

async function createFixture(platform = 'civitai', pageId = '123') {
  await TestBed.configureTestingModule({
    imports: [CatalogDetail],
    providers: [
      provideRouter([{ path: '**', redirectTo: '' }]),
      { provide: ActivatedRoute, useValue: makeRoute(platform, pageId) },
      { provide: ModelService, useValue: mockModelService },
      { provide: DownloadService, useValue: mockDownloadService },
      { provide: WorkflowService, useValue: mockWorkflowService },
      { provide: NotificationService, useValue: mockNotifService },
    ],
  }).compileComponents();

  const fixture = TestBed.createComponent(CatalogDetail);
  fixture.detectChanges();
  await fixture.whenStable();
  return fixture;
}

describe('CatalogDetail component', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockModelService.getCatalogEntry.mockReturnValue(of(mockEntry));
    mockModelService.getMetadata.mockReturnValue(of(mockMeta));
  });

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

  it('removeFromCatalog calls service and navigates to /catalog', async () => {
    mockModelService.removeCatalogEntry.mockReturnValue(of(undefined));
    const fixture = await createFixture();
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigate');
    fixture.componentInstance.removeFromCatalog();
    expect(mockModelService.removeCatalogEntry).toHaveBeenCalledWith('civitai', '123');
    expect(navigateSpy).toHaveBeenCalledWith(['/catalog']);
  });

  it('does not load primaryMeta when no installed files', async () => {
    const fixture = await createFixture();
    expect(mockModelService.getMetadata).not.toHaveBeenCalled();
    expect(fixture.componentInstance.primaryMeta()).toBeNull();
  });

  it('loads primaryMeta when entry has installed files', async () => {
    mockModelService.getCatalogEntry.mockReturnValue(
      of({ ...mockEntry, installed_files: [mockInstalledFile] }),
    );
    const fixture = await createFixture();
    expect(mockModelService.getMetadata).toHaveBeenCalledWith('loras', 'test.safetensors');
    expect(fixture.componentInstance.primaryMeta()?.description).toBe('A test model');
  });

  it('sets primaryType and primaryPath from first installed file', async () => {
    mockModelService.getCatalogEntry.mockReturnValue(
      of({ ...mockEntry, installed_files: [mockInstalledFile] }),
    );
    const fixture = await createFixture();
    expect(fixture.componentInstance.primaryType).toBe('loras');
    expect(fixture.componentInstance.primaryPath).toBe('test.safetensors');
  });

  it('shows edit button when installed files present', async () => {
    mockModelService.getCatalogEntry.mockReturnValue(
      of({ ...mockEntry, installed_files: [mockInstalledFile] }),
    );
    const fixture = await createFixture();
    fixture.detectChanges();
    const buttons = fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLElement>;
    const labels = Array.from(buttons).map((b) => b.textContent?.trim());
    expect(labels).toContain('Edit');
  });

  it('enterEdit sets editMode true', async () => {
    mockModelService.getCatalogEntry.mockReturnValue(
      of({ ...mockEntry, installed_files: [mockInstalledFile] }),
    );
    const fixture = await createFixture();
    fixture.componentInstance.enterEdit();
    expect(fixture.componentInstance.editMode()).toBe(true);
  });

  it('cancelEdit sets editMode false', async () => {
    mockModelService.getCatalogEntry.mockReturnValue(
      of({ ...mockEntry, installed_files: [mockInstalledFile] }),
    );
    const fixture = await createFixture();
    fixture.componentInstance.enterEdit();
    fixture.componentInstance.cancelEdit();
    expect(fixture.componentInstance.editMode()).toBe(false);
  });

  it('save() calls updateMetadataWithPath with primaryType and primaryPath', async () => {
    mockModelService.getCatalogEntry.mockReturnValue(
      of({ ...mockEntry, installed_files: [mockInstalledFile] }),
    );
    mockModelService.updateMetadataWithPath.mockReturnValue(of({ new_path: 'test.safetensors' }));
    const fixture = await createFixture();
    fixture.componentInstance.enterEdit();
    fixture.componentInstance.save();
    expect(mockModelService.updateMetadataWithPath).toHaveBeenCalledWith(
      'loras',
      'test.safetensors',
      expect.any(Object),
    );
  });

  it('save() updates primaryPath when new_path differs', async () => {
    mockModelService.getCatalogEntry.mockReturnValue(
      of({ ...mockEntry, installed_files: [mockInstalledFile] }),
    );
    mockModelService.updateMetadataWithPath.mockReturnValue(
      of({ new_path: 'Pony/test.safetensors' }),
    );
    const fixture = await createFixture();
    fixture.componentInstance.enterEdit();
    fixture.componentInstance.save();
    expect(fixture.componentInstance.primaryPath).toBe('Pony/test.safetensors');
  });
});
