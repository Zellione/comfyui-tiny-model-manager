import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { Subject, of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { CatalogDetail } from './catalog-detail';
import { ModelService, CatalogEntryDetail, InstalledFile } from '../../services/model';
import { DownloadService, DownloadTask } from '../../services/download';
import { WorkflowService } from '../../services/workflow';
import { NotificationService } from '../../services/notification';
import { KeywordsService } from '../../services/keywords';
import { FilenameKeyword } from '../../utils/filename-detector';

const mockInstalledFile: InstalledFile = {
  filename: 'test.safetensors',
  model_type: 'loras',
  size_bytes: 1024,
  modified_at: 0,
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
  description: '',
  trigger_words: [],
  tags: [],
  media: [],
};

const mockModelService = {
  getCatalogEntry: vi.fn(),
  removeCatalogEntry: vi.fn(),
  getRepoFiles: vi.fn(),
  updateMetadata: vi.fn(),
  updateMetadataWithPath: vi.fn(),
  updateCatalogMetadata: vi.fn(),
  refetchCatalog: vi.fn(),
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

const mockKeywordsService = {
  getKeywords: vi.fn(() => of([] as FilenameKeyword[])),
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
      { provide: KeywordsService, useValue: mockKeywordsService },
      provideTranslateServiceForTests(),
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
    mockModelService.getRepoFiles.mockReturnValue(of([]));
    mockModelService.updateMetadata.mockReturnValue(of(undefined));
    mockModelService.updateMetadataWithPath.mockReturnValue(of({ new_path: 'test.safetensors' }));
    mockModelService.updateCatalogMetadata.mockReturnValue(of(undefined));
    mockModelService.refetchCatalog.mockReturnValue(of(mockEntry));
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

  it('removeFromCatalog calls service and navigates to /catalog', async () => {
    mockModelService.removeCatalogEntry.mockReturnValue(of(undefined));
    const fixture = await createFixture();
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigate');
    fixture.componentInstance.removeFromCatalog();
    expect(mockModelService.removeCatalogEntry).toHaveBeenCalledWith('civitai', '123');
    expect(navigateSpy).toHaveBeenCalledWith(['/catalog']);
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

  it('save() writes catalog-owned metadata for the entry', async () => {
    mockModelService.getCatalogEntry.mockReturnValue(
      of({ ...mockEntry, installed_files: [mockInstalledFile] }),
    );
    const fixture = await createFixture();
    fixture.componentInstance.enterEdit();
    fixture.componentInstance.save();
    expect(mockModelService.updateCatalogMetadata).toHaveBeenCalledWith(
      'civitai',
      '123',
      expect.objectContaining({
        description: expect.any(String),
        trigger_words: expect.any(Array),
        tags: expect.any(Array),
      }),
    );
  });

  it('save() sends per-file base model changes and reloads the entry', async () => {
    const downloadedRepoFile = {
      ...mockEntry.repo_files[0],
      is_downloaded: true,
      installed_path: 'test.safetensors',
      base_model: '',
    };
    mockModelService.getCatalogEntry.mockReturnValue(
      of({ ...mockEntry, installed_files: [mockInstalledFile] }),
    );
    mockModelService.getRepoFiles.mockReturnValue(of([downloadedRepoFile]));
    const fixture = await createFixture();
    fixture.componentInstance.enterEdit();
    fixture.componentInstance.setFileBaseModel('test.safetensors', 'Pony');
    mockModelService.getCatalogEntry.mockClear();
    fixture.componentInstance.save();
    // The changed file is moved/updated via updateMetadata...
    expect(mockModelService.updateMetadata).toHaveBeenCalledWith('loras', 'test.safetensors', {
      base_model: 'Pony',
    });
    // ...and the catalog entry is reloaded so the move is reflected.
    expect(mockModelService.getCatalogEntry).toHaveBeenCalled();
  });

  it('refetch() pulls fresh catalog metadata from source and applies it', async () => {
    const refreshed = { ...mockEntry, description: 'fresh from source' };
    mockModelService.refetchCatalog.mockReturnValue(of(refreshed));
    const fixture = await createFixture();
    fixture.componentInstance.refetch();
    expect(mockModelService.refetchCatalog).toHaveBeenCalledWith('civitai', '123');
    expect(fixture.componentInstance.displayDescription()).toBe('fresh from source');
    expect(mockNotifService.show).toHaveBeenCalledWith(
      'success',
      expect.stringContaining('re-fetched'),
    );
    expect(fixture.componentInstance.refetching()).toBe(false);
  });

  it('displays catalog-owned metadata with zero files installed', async () => {
    mockModelService.getCatalogEntry.mockReturnValue(
      of({
        ...mockEntry,
        installed_files: [],
        description: 'standalone desc',
        trigger_words: ['kw1'],
        tags: ['anime'],
        media: [{ id: 0, media_type: 'image', local_path: '/m/0.jpg' }],
      }),
    );
    const fixture = await createFixture();
    expect(fixture.componentInstance.displayDescription()).toBe('standalone desc');
    expect(fixture.componentInstance.displayTriggerWords()).toEqual(['kw1']);
    expect(fixture.componentInstance.displayTags()).toEqual(['anime']);
    expect(fixture.componentInstance.displayMedia().length).toBe(1);
  });

  it('save() does not send base model updates for unchanged files', async () => {
    const downloadedRepoFile = {
      ...mockEntry.repo_files[0],
      is_downloaded: true,
      installed_path: 'test.safetensors',
      base_model: 'SDXL 1.0',
    };
    mockModelService.getCatalogEntry.mockReturnValue(
      of({ ...mockEntry, installed_files: [mockInstalledFile] }),
    );
    mockModelService.getRepoFiles.mockReturnValue(of([downloadedRepoFile]));
    const fixture = await createFixture();
    fixture.componentInstance.enterEdit();
    fixture.componentInstance.save();
    expect(mockModelService.updateMetadata).not.toHaveBeenCalled();
  });

  it('save() shows error notification on failure', async () => {
    mockModelService.updateCatalogMetadata.mockReturnValue(
      throwError(() => new Error('save failed')),
    );
    const fixture = await createFixture();
    fixture.componentInstance.enterEdit();
    fixture.componentInstance.save();
    expect(mockNotifService.show).toHaveBeenCalledWith('error', 'save failed');
  });

  it('sourceName returns generic source for unknown platform', async () => {
    const fixture = await createFixture('unknown_platform', '999');
    expect(fixture.componentInstance.sourceName()).toBe('source');
  });

  it('refetch() shows error notification on failure', async () => {
    mockModelService.refetchCatalog.mockReturnValue(throwError(() => new Error('network error')));
    const fixture = await createFixture();
    fixture.componentInstance.refetch();
    expect(mockNotifService.show).toHaveBeenCalledWith('error', 'network error');
    expect(fixture.componentInstance.refetching()).toBe(false);
  });

  it('removeFromCatalog() shows error notification on failure', async () => {
    mockModelService.removeCatalogEntry.mockReturnValue(
      throwError(() => new Error('remove failed')),
    );
    const fixture = await createFixture();
    fixture.componentInstance.removeFromCatalog();
    expect(mockNotifService.show).toHaveBeenCalledWith('error', expect.any(String));
    expect(fixture.componentInstance.removing()).toBe(false);
  });

  it('uninstallRepoFile() shows success and reloads on success', async () => {
    mockModelService.deleteModel.mockReturnValue(of(undefined));
    const fixture = await createFixture();
    fixture.componentInstance.uninstallRepoFile(mockEntry.repo_files[0]);
    expect(mockModelService.deleteModel).toHaveBeenCalled();
    expect(mockNotifService.show).toHaveBeenCalledWith('success', expect.any(String));
  });

  it('uninstallRepoFile() shows error on failure', async () => {
    mockModelService.deleteModel.mockReturnValue(throwError(() => new Error('locked')));
    const fixture = await createFixture();
    fixture.componentInstance.uninstallRepoFile(mockEntry.repo_files[0]);
    expect(mockNotifService.show).toHaveBeenCalledWith('error', 'locked');
    expect(fixture.componentInstance.deleting()).toBe(false);
  });

  it('addRepoFileToWorkflow() shows success notification', async () => {
    mockWorkflowService.addToWorkflow.mockReturnValue(of(undefined));
    const fixture = await createFixture();
    fixture.componentInstance.addRepoFileToWorkflow(mockEntry.repo_files[0]);
    expect(mockNotifService.show).toHaveBeenCalledWith('success', expect.any(String));
  });

  it('addRepoFileToWorkflow() shows error notification on failure', async () => {
    mockWorkflowService.addToWorkflow.mockReturnValue(throwError(() => new Error('fail')));
    const fixture = await createFixture();
    fixture.componentInstance.addRepoFileToWorkflow(mockEntry.repo_files[0]);
    expect(mockNotifService.show).toHaveBeenCalledWith('error', expect.any(String));
  });

  it('downloadFile() shows success notification when download starts', async () => {
    mockDownloadService.startDownload.mockReturnValue(of({}));
    const fixture = await createFixture();
    fixture.componentInstance.downloadFile(mockEntry.repo_files[0]);
    expect(mockDownloadService.startDownload).toHaveBeenCalled();
    expect(mockNotifService.show).toHaveBeenCalledWith('success', expect.any(String));
  });

  it('downloadFile() shows error notification on failure', async () => {
    mockDownloadService.startDownload.mockReturnValue(throwError(() => new Error('dl failed')));
    const fixture = await createFixture();
    fixture.componentInstance.downloadFile(mockEntry.repo_files[0]);
    expect(mockNotifService.show).toHaveBeenCalledWith('error', expect.any(String));
  });

  it('downloadFile() does nothing when file has no download_url', async () => {
    const fixture = await createFixture();
    fixture.componentInstance.downloadFile({ ...mockEntry.repo_files[0], download_url: '' });
    expect(mockDownloadService.startDownload).not.toHaveBeenCalled();
  });

  it('activeTaskMap() maps task by filename', async () => {
    const task: DownloadTask = {
      id: 'task-1',
      url: 'https://example.com/test.safetensors',
      model_type: 'loras',
      filename: 'test.safetensors',
      platform: 'civitai',
      source_id: '123',
      status: 'downloading',
      progress: 50,
      downloaded_bytes: 512,
      total_bytes: 1024,
      error: null,
      history_id: null,
    };
    mockDownloadService.activeTasks$ = of([
      task,
    ]) as unknown as typeof mockDownloadService.activeTasks$;
    const fixture = await createFixture();
    expect(fixture.componentInstance.activeTaskMap().get('test.safetensors')).toEqual(task);
  });

  it('loadRepoFiles() populates fileBaseModels for downloaded files', async () => {
    const downloadedFile = {
      ...mockEntry.repo_files[0],
      is_downloaded: true,
      base_model: 'SDXL 1.0',
    };
    mockModelService.getCatalogEntry.mockReturnValue(
      of({ ...mockEntry, installed_files: [mockInstalledFile] }),
    );
    mockModelService.getRepoFiles.mockReturnValue(of([downloadedFile]));
    const fixture = await createFixture();
    expect(fixture.componentInstance.fileBaseModels()['test.safetensors']).toBe('SDXL 1.0');
  });

  it('repoFileFullSubLabel includes civitai_version_name for downloaded files', async () => {
    const fixture = await createFixture();
    const comp = fixture.componentInstance;
    const rf = {
      ...mockEntry.repo_files[0],
      is_downloaded: true,
      size_bytes: 1024,
      civitai_version_name: 'v2 Turbo',
    };
    const label = comp.repoFileFullSubLabel(rf);
    expect(label).toContain('v2 Turbo');
  });

  it('repoFileFullSubLabel omits version name when empty', async () => {
    const fixture = await createFixture();
    const comp = fixture.componentInstance;
    const rf = {
      ...mockEntry.repo_files[0],
      is_downloaded: true,
      size_bytes: 1024,
      civitai_version_name: '',
    };
    const label = comp.repoFileFullSubLabel(rf);
    expect(label).not.toContain('·  ·');
  });

  it('repoFileFullSubLabel includes model_type, base_model, and version for non-downloaded files', async () => {
    const fixture = await createFixture();
    const comp = fixture.componentInstance;
    const rf = {
      ...mockEntry.repo_files[0],
      is_downloaded: false,
      size_bytes: 1024,
      civitai_version_name: 'v0.3',
    };
    const label = comp.repoFileFullSubLabel(rf);
    expect(label).toContain('loras');
    expect(label).toContain('SDXL');
    expect(label).toContain('v0.3');
  });
});

describe('CatalogDetail — F-82 downloadFile base model detection', () => {
  const sdxlKeyword = {
    id: 1,
    keyword: 'sdxl',
    base_model: 'SDXL 1.0',
    model_type: null,
    sort_order: 10,
  };

  const sdxlRepoFile = {
    filename: 'sdxl_model.safetensors',
    model_type: 'checkpoints' as const,
    size_bytes: 1024,
    download_url: 'https://example.com/sdxl_model.safetensors',
    source_page_url: '',
    is_downloaded: false,
    added_at: null,
    installed_path: '',
    base_model: '',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockModelService.getCatalogEntry.mockReturnValue(of(mockEntry));
    mockModelService.getRepoFiles.mockReturnValue(of([]));
    mockKeywordsService.getKeywords.mockReturnValue(of([]));
    mockDownloadService.startDownload.mockReturnValue(of(undefined));
  });

  afterEach(() => TestBed.resetTestingModule());

  it('passes detected base model to startDownload when a keyword matches the filename', async () => {
    mockKeywordsService.getKeywords.mockReturnValue(of([sdxlKeyword]));
    const fixture = await createFixture();
    fixture.componentInstance.downloadFile(sdxlRepoFile);
    expect(mockDownloadService.startDownload).toHaveBeenCalledWith(
      'https://example.com/sdxl_model.safetensors',
      'checkpoints',
      'sdxl_model.safetensors',
      'civitai',
      expect.any(String),
      'SDXL 1.0',
    );
  });

  it('passes empty base model to startDownload when no keyword matches the filename', async () => {
    const fixture = await createFixture();
    fixture.componentInstance.downloadFile(sdxlRepoFile);
    expect(mockDownloadService.startDownload).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(String),
      expect.any(String),
      expect.any(String),
      expect.any(String),
      '',
    );
  });
});

describe('CatalogDetail — copyTriggerWords', () => {
  let clipboardWriteText: ReturnType<typeof vi.fn>;
  let originalNavigator: typeof navigator;

  beforeEach(() => {
    vi.clearAllMocks();
    originalNavigator = globalThis.navigator;
    clipboardWriteText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText: clipboardWriteText } });
    mockModelService.getCatalogEntry.mockReturnValue(of(mockEntry));
    mockModelService.getRepoFiles.mockReturnValue(of([]));
  });

  afterEach(() => {
    vi.stubGlobal('navigator', originalNavigator);
    TestBed.resetTestingModule();
  });

  it('does nothing when entry has no trigger words', async () => {
    const fixture = await createFixture();
    fixture.componentInstance.copyTriggerWords();
    expect(clipboardWriteText).not.toHaveBeenCalled();
  });

  it('copies joined trigger words to clipboard', async () => {
    mockModelService.getCatalogEntry.mockReturnValue(
      of({ ...mockEntry, trigger_words: ['alpha', 'beta'] }),
    );
    const fixture = await createFixture();
    fixture.componentInstance.copyTriggerWords();
    expect(clipboardWriteText).toHaveBeenCalledWith('alpha, beta');
  });

  it('sets copied signal after successful clipboard write', async () => {
    mockModelService.getCatalogEntry.mockReturnValue(of({ ...mockEntry, trigger_words: ['word'] }));
    const fixture = await createFixture();
    fixture.componentInstance.copyTriggerWords();
    await fixture.whenStable();
    expect(fixture.componentInstance.copied()).toBe(true);
  });
});

describe('CatalogDetail — repoFileSourceId paths', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockModelService.getRepoFiles.mockReturnValue(of([]));
    mockDownloadService.startDownload.mockReturnValue(of({}));
  });

  afterEach(() => TestBed.resetTestingModule());

  it('uses entry source_page_id as sourceId for huggingface downloads', async () => {
    mockModelService.getCatalogEntry.mockReturnValue(
      of({ ...mockEntry, source_platform: 'huggingface', source_page_id: 'user/repo' }),
    );
    const fixture = await createFixture('huggingface', 'user/repo');
    fixture.componentInstance.downloadFile({
      ...mockEntry.repo_files[0],
      download_url: 'https://huggingface.co/user/repo/resolve/main/test.safetensors',
    });
    expect(mockDownloadService.startDownload).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(String),
      expect.any(String),
      'huggingface',
      'user/repo',
      '',
    );
  });

  it('extracts modelVersionId from civitai source_page_url as sourceId', async () => {
    mockModelService.getCatalogEntry.mockReturnValue(of(mockEntry));
    const fixture = await createFixture();
    fixture.componentInstance.downloadFile({
      ...mockEntry.repo_files[0],
      source_page_url: 'https://civitai.com/models/123?modelVersionId=456',
    });
    expect(mockDownloadService.startDownload).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(String),
      expect.any(String),
      'civitai',
      '456',
      '',
    );
  });

  it('returns empty sourceId for invalid civitai source_page_url', async () => {
    mockModelService.getCatalogEntry.mockReturnValue(of(mockEntry));
    const fixture = await createFixture();
    fixture.componentInstance.downloadFile({
      ...mockEntry.repo_files[0],
      source_page_url: 'not-a-valid-url',
    });
    expect(mockDownloadService.startDownload).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(String),
      expect.any(String),
      'civitai',
      '',
      '',
    );
  });
});

describe('CatalogDetail — cancelEdit restores per-file base models', () => {
  afterEach(() => TestBed.resetTestingModule());

  it('restores fileBaseModels from downloaded repo files', async () => {
    vi.clearAllMocks();
    mockModelService.getCatalogEntry.mockReturnValue(
      of({ ...mockEntry, installed_files: [mockInstalledFile] }),
    );
    mockModelService.getRepoFiles.mockReturnValue(
      of([{ ...mockEntry.repo_files[0], is_downloaded: true, base_model: 'SDXL 1.0' }]),
    );
    const fixture = await createFixture();
    fixture.componentInstance.setFileBaseModel('test.safetensors', 'Pony');
    fixture.componentInstance.cancelEdit();
    expect(fixture.componentInstance.fileBaseModels()['test.safetensors']).toBe('SDXL 1.0');
  });
});

describe('CatalogDetail — completedTasks$ handler', () => {
  afterEach(() => TestBed.resetTestingModule());

  it('shows error notification for a completed error task matching a repo file', async () => {
    vi.clearAllMocks();
    const completedTasks$ = new Subject<DownloadTask>();
    (mockDownloadService as any).completedTasks$ = completedTasks$;
    mockModelService.getCatalogEntry.mockReturnValue(of(mockEntry));
    mockModelService.getRepoFiles.mockReturnValue(of([]));

    await createFixture();
    const errorTask: DownloadTask = {
      id: 'task-1',
      url: '',
      model_type: 'loras',
      filename: 'test.safetensors',
      platform: 'civitai',
      source_id: '123',
      status: 'error',
      progress: 0,
      downloaded_bytes: 0,
      total_bytes: 0,
      error: 'disk full',
      history_id: null,
    };
    completedTasks$.next(errorTask);

    expect(mockNotifService.show).toHaveBeenCalledWith('error', expect.any(String));
    (mockDownloadService as any).completedTasks$ = of([]);
  });

  it('adds file to finalizingFiles for a completed done task matching a repo file', async () => {
    vi.clearAllMocks();
    const completedTasks$ = new Subject<DownloadTask>();
    (mockDownloadService as any).completedTasks$ = completedTasks$;
    mockModelService.getCatalogEntry.mockReturnValue(of(mockEntry));
    mockModelService.getRepoFiles.mockReturnValue(of([]));

    const fixture = await createFixture();
    const doneTask: DownloadTask = {
      id: 'task-2',
      url: '',
      model_type: 'loras',
      filename: 'test.safetensors',
      platform: 'civitai',
      source_id: '123',
      status: 'done',
      progress: 100,
      downloaded_bytes: 1024,
      total_bytes: 1024,
      error: null,
      history_id: null,
    };
    completedTasks$.next(doneTask);

    expect(fixture.componentInstance.finalizingFiles().has('test.safetensors')).toBe(true);
    (mockDownloadService as any).completedTasks$ = of([]);
  });

  it('triggers pollUntilDownloaded and drops from finalizingFiles when file is confirmed downloaded', async () => {
    vi.clearAllMocks();
    const completedTasks$ = new Subject<DownloadTask>();
    (mockDownloadService as any).completedTasks$ = completedTasks$;
    const downloadedEntry = {
      ...mockEntry,
      repo_files: [{ ...mockEntry.repo_files[0], is_downloaded: true }],
    };
    mockModelService.getCatalogEntry.mockReturnValue(of(downloadedEntry));
    mockModelService.getRepoFiles.mockReturnValue(of([]));

    const fixture = await createFixture();
    const doneTask: DownloadTask = {
      id: 'task-3',
      url: '',
      model_type: 'loras',
      filename: 'test.safetensors',
      platform: 'civitai',
      source_id: '123',
      status: 'done',
      progress: 100,
      downloaded_bytes: 1024,
      total_bytes: 1024,
      error: null,
      history_id: null,
    };
    completedTasks$.next(doneTask);

    expect(fixture.componentInstance.finalizingFiles().has('test.safetensors')).toBe(false);
    (mockDownloadService as any).completedTasks$ = of([]);
  });
});
