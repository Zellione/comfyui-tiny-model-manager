import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { EMPTY, of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { ModelDetail } from './model-detail';
import {
  ModelService,
  RepoFile,
  CatalogEntryDetail,
  RefetchPreviewResponse,
} from '../../services/model';
import { DownloadService } from '../../services/download';
import { WorkflowService } from '../../services/workflow';
import { NotificationService } from '../../services/notification';
import { KeywordsService } from '../../services/keywords';

const makeCatalogEntry = (overrides: Partial<CatalogEntryDetail> = {}): CatalogEntryDetail => ({
  id: 1,
  source_platform: 'civitai',
  source_page_id: '1',
  source_page_url: '',
  display_name: '',
  thumbnail_url: '',
  base_model: '',
  created_at: '',
  model_type: 'loras',
  is_empty: false,
  installed_files: [],
  repo_files: [],
  description: '',
  trigger_words: [],
  tags: [],
  media: [],
  ...overrides,
});

const makeMeta = (overrides = {}) => ({
  description: 'A test model',
  trigger_words: ['foo', 'bar'],
  tags: ['portrait'],
  media: [],
  base_model: 'SDXL 1.0',
  source_platform: 'civitai',
  source_url: 'https://civitai.com/models/1',
  size_bytes: 1073741824, // 1 GB
  ...overrides,
});

const makeRepoFile = (overrides: Partial<RepoFile> = {}): RepoFile => ({
  filename: 'companion.safetensors',
  model_type: 'loras',
  size_bytes: 1048576,
  download_url: 'https://civitai.com/api/download/models/99999?token=abc',
  source_page_url: 'https://civitai.com/models/1',
  is_downloaded: false,
  added_at: null,
  installed_path: '',
  base_model: '',
  ...overrides,
});

const makePreviewData = (
  overrides: Partial<RefetchPreviewResponse> = {},
): RefetchPreviewResponse => ({
  old: {
    description: 'Old desc',
    trigger_words: [],
    tags: [],
    base_model: '',
    media: [],
    last_edited_at: { description: null, trigger_words: null, tags: null, base_model: null },
  },
  new: {
    description: 'New desc',
    trigger_words: [],
    tags: [],
    base_model: '',
    media_urls: [],
  },
  expires_at: new Date(Date.now() + 300_000).toISOString(),
  no_changes: false,
  ...overrides,
});

const mockModelService = {
  getMetadata: vi.fn(() => of(makeMeta())),
  updateMetadata: vi.fn(() => of(undefined)),
  updateMetadataWithPath: vi.fn(() => of({ new_path: 'my-lora.safetensors' })),
  refetchMetadata: vi.fn(() => of({ removed: false, meta: makeMeta() })),
  refetchPreview: vi.fn(() => of(makePreviewData())),
  refetchApply: vi.fn(() => of({ removed: false, meta: makeMeta() })),
  deleteModel: vi.fn(() => of(undefined)),
  getModelTypes: vi.fn(() => of(['checkpoints', 'loras'])),
  moveModel: vi.fn(() => of(undefined)),
  getRepoFiles: vi.fn(() => of([] as RepoFile[])),
  getCatalogEntry: vi.fn(() => of(null)),
  linkSource: vi.fn(() => of(undefined)),
};

const mockDownloadService = {
  startDownload: vi.fn(() => of({ task_id: 'abc' })),
  activeTasks$: EMPTY,
  completedTasks$: EMPTY,
};

const mockWorkflowService = { addToWorkflow: vi.fn(() => of(undefined)) };
const mockNotifService = { show: vi.fn() };
const mockKeywordsService = { getKeywords: vi.fn(() => of([])) };

describe('ModelDetail', () => {
  let component: ModelDetail;
  let router: Router;

  beforeEach(async () => {
    vi.clearAllMocks();
    await TestBed.configureTestingModule({
      imports: [ModelDetail],
      providers: [
        provideRouter([{ path: 'models', children: [] }]),
        { provide: ModelService, useValue: mockModelService },
        { provide: DownloadService, useValue: mockDownloadService },
        { provide: WorkflowService, useValue: mockWorkflowService },
        { provide: NotificationService, useValue: mockNotifService },
        { provide: KeywordsService, useValue: mockKeywordsService },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(ModelDetail);
    component = fixture.componentInstance;
    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate').mockResolvedValue(true);
    component.modelType = 'loras';
    component.modelPath = 'my-lora.safetensors';
    component.editType = 'loras';
    component.meta.set(makeMeta());
    component.loading.set(false);
  });

  describe('enterEdit / cancelEdit', () => {
    it('enterEdit() sets editMode to true', () => {
      component.enterEdit();
      expect(component.editMode()).toBe(true);
    });

    it('cancelEdit() sets editMode to false', () => {
      component.enterEdit();
      component.cancelEdit();
      expect(component.editMode()).toBe(false);
    });

    it('cancelEdit() resets editMeta to current meta values', () => {
      component.editMeta = { description: 'changed', trigger_words: ['new'] };
      component.cancelEdit();
      expect(component.editMeta.description).toBe('A test model');
      expect(component.editMeta.trigger_words).toEqual(['foo', 'bar']);
    });
  });

  describe('uninstall', () => {
    it('calls deleteModel with modelType and modelPath', () => {
      component.uninstall();
      expect(mockModelService.deleteModel).toHaveBeenCalledWith('loras', 'my-lora.safetensors');
    });

    it('shows success notification on successful delete', () => {
      component.uninstall();
      expect(mockNotifService.show).toHaveBeenCalledWith(
        'success',
        expect.stringContaining('uninstalled'),
      );
    });

    it('shows notification on error', () => {
      mockModelService.deleteModel.mockReturnValueOnce(throwError(() => new Error('disk full')));
      component.uninstall();
      expect(mockNotifService.show).toHaveBeenCalledWith('error', 'disk full');
      expect(component.deleting()).toBe(false);
    });
  });

  describe('triggerRefetchPreview', () => {
    it('calls refetchPreview on the service', () => {
      component.triggerRefetchPreview();
      expect(mockModelService.refetchPreview).toHaveBeenCalledWith('loras', 'my-lora.safetensors');
    });

    it('sets showRefetchModal when no_changes is false', () => {
      mockModelService.refetchPreview.mockReturnValueOnce(
        of(makePreviewData({ no_changes: false })),
      );
      component.triggerRefetchPreview();
      expect(component.showRefetchModal()).toBe(true);
      expect(component.refetchNoChanges()).toBe(false);
    });

    it('sets refetchNoChanges when no_changes is true (no modal)', () => {
      mockModelService.refetchPreview.mockReturnValueOnce(
        of(makePreviewData({ no_changes: true })),
      );
      component.triggerRefetchPreview();
      expect(component.refetchNoChanges()).toBe(true);
      expect(component.showRefetchModal()).toBe(false);
    });

    it('navigates to /models and notifies when the stale record was pruned', () => {
      mockModelService.refetchPreview.mockReturnValueOnce(
        of({ removed: true } as RefetchPreviewResponse),
      );
      component.triggerRefetchPreview();
      expect(mockNotifService.show).toHaveBeenCalledWith(
        'success',
        expect.stringContaining('no longer on disk'),
      );
      expect(router.navigate).toHaveBeenCalledWith(['/models']);
    });
  });

  describe('onModalApplied', () => {
    it('updates meta signal and closes modal', () => {
      component.showRefetchModal.set(true);
      const newMeta = makeMeta({ description: 'applied' });
      component.onModalApplied(newMeta);
      expect(component.meta()?.description).toBe('applied');
      expect(component.showRefetchModal()).toBe(false);
    });

    it('shows success notification', () => {
      component.onModalApplied(makeMeta());
      expect(mockNotifService.show).toHaveBeenCalledWith('success', expect.any(String));
    });

    it('calls loadRepoFiles (getRepoFiles is invoked)', () => {
      vi.clearAllMocks();
      component.onModalApplied(makeMeta());
      expect(mockModelService.getRepoFiles).toHaveBeenCalled();
    });
  });

  describe('reviewAnyway', () => {
    it('clears no-changes flag and shows modal', () => {
      component.refetchNoChanges.set(true);
      component.refetchPreviewData.set(makePreviewData());
      component.reviewAnyway();
      expect(component.refetchNoChanges()).toBe(false);
      expect(component.showRefetchModal()).toBe(true);
    });
  });

  describe('formatBytes', () => {
    it('returns empty string for 0', () => {
      expect(component.formatBytes(0)).toBe('');
    });

    it('formats bytes', () => {
      expect(component.formatBytes(512)).toBe('512.0 B');
    });

    it('formats megabytes', () => {
      expect(component.formatBytes(57400000)).toMatch(/MB/);
    });

    it('formats gigabytes', () => {
      expect(component.formatBytes(1073741824)).toBe('1.0 GB');
    });
  });

  describe('eyebrowParts', () => {
    it('includes modelType, formatted size, and base_model', () => {
      const parts = component.eyebrowParts();
      expect(parts).toContain('loras');
      expect(parts.some((p) => p.includes('GB'))).toBe(true);
      expect(parts).toContain('SDXL 1.0');
    });

    it('omits size when zero but keeps base_model', () => {
      component.meta.set(makeMeta({ base_model: 'SDXL 1.0', size_bytes: 0 }));
      const parts = component.eyebrowParts();
      expect(parts).toEqual(['loras', 'SDXL 1.0']); // size omitted, base_model present
    });

    it('orders parts as type → base_model → size', () => {
      component.meta.set(makeMeta({ base_model: 'Flux', size_bytes: 1024 * 1024 }));
      const parts = component.eyebrowParts();
      expect(parts[0]).toBe('loras');
      expect(parts[1]).toBe('Flux');
      expect(parts[2]).toMatch(/MB/);
    });
  });

  describe('sourceName', () => {
    it('returns CivitAI for civitai platform', () => {
      expect(component.sourceName()).toBe('CivitAI');
    });

    it('returns HuggingFace for huggingface platform', () => {
      component.meta.set(makeMeta({ source_platform: 'huggingface' }));
      expect(component.sourceName()).toBe('HuggingFace');
    });

    it('returns source for unknown platform', () => {
      component.meta.set(makeMeta({ source_platform: '' }));
      expect(component.sourceName()).toBe('source');
    });
  });

  describe('save exits edit mode', () => {
    it('exits editMode on successful save without type change', () => {
      component.enterEdit();
      component.save();
      expect(component.editMode()).toBe(false);
    });
  });

  describe('loadRepoFiles', () => {
    it('populates repoFiles signal on success', () => {
      const files = [makeRepoFile()];
      mockModelService.getRepoFiles.mockReturnValueOnce(of(files));
      component.loadRepoFiles();
      expect(component.repoFiles()).toEqual(files);
    });

    it('falls back to empty array on error', () => {
      mockModelService.getRepoFiles.mockReturnValueOnce(
        throwError(() => new Error('network error')),
      );
      component.loadRepoFiles();
      expect(component.repoFiles()).toEqual([]);
    });
  });

  describe('displayTitle', () => {
    it('falls back to modelBasename when catalogEntry is null', () => {
      component.catalogEntry.set(null);
      expect(component.displayTitle()).toBe('my-lora.safetensors');
    });

    it('returns display_name from catalog entry when set', () => {
      component.catalogEntry.set(
        makeCatalogEntry({ display_name: 'My Awesome LoRA', base_model: 'SDXL' }),
      );
      expect(component.displayTitle()).toBe('My Awesome LoRA');
    });

    it('falls back to modelBasename when catalog display_name is empty', () => {
      component.catalogEntry.set(makeCatalogEntry({ display_name: '' }));
      expect(component.displayTitle()).toBe('my-lora.safetensors');
    });
  });

  describe('linkSource', () => {
    it('showLinkSourcePanel is true when source_url is empty', () => {
      component.meta.set(makeMeta({ source_url: '' }));
      expect(component.showLinkSourcePanel()).toBe(true);
    });

    it('showLinkSourcePanel is false when source_url is set', () => {
      component.meta.set(makeMeta({ source_url: 'https://civitai.com/models/1' }));
      expect(component.showLinkSourcePanel()).toBe(false);
    });

    it('calls linkSource service with trimmed URL', () => {
      component.linkSourceUrl.set('  https://civitai.com/models/123  ');
      component.linkSource();
      expect(mockModelService.linkSource).toHaveBeenCalledWith(
        'loras',
        'my-lora.safetensors',
        'https://civitai.com/models/123',
      );
    });

    it('does nothing when URL is empty', () => {
      component.linkSourceUrl.set('');
      component.linkSource();
      expect(mockModelService.linkSource).not.toHaveBeenCalled();
    });

    it('shows success notification and navigates to /models on success', () => {
      component.linkSourceUrl.set('https://civitai.com/models/42');
      component.linkSource();
      expect(mockNotifService.show).toHaveBeenCalledWith('success', expect.any(String));
      expect(router.navigate).toHaveBeenCalledWith(['/models']);
    });

    it('sets linkSourceError on failure', () => {
      mockModelService.linkSource.mockReturnValueOnce(throwError(() => new Error('bad URL')));
      component.linkSourceUrl.set('https://example.com/bad');
      component.linkSource();
      expect(component.linkSourceError()).toBe('bad URL');
      expect(component.linking()).toBe(false);
    });
  });

  describe('addFileToWorkflow', () => {
    it('uses installed_path when set', () => {
      const file = makeRepoFile({
        is_downloaded: true,
        installed_path: 'sub/companion.safetensors',
      });
      component.addFileToWorkflow(file);
      expect(mockWorkflowService.addToWorkflow).toHaveBeenCalledWith(
        'loras',
        'sub/companion.safetensors',
      );
    });

    it('falls back to filename when installed_path is empty', () => {
      const file = makeRepoFile({ is_downloaded: true, installed_path: '' });
      component.addFileToWorkflow(file);
      expect(mockWorkflowService.addToWorkflow).toHaveBeenCalledWith(
        'loras',
        'companion.safetensors',
      );
    });
  });

  describe('deleteFile', () => {
    it('deletes file and reloads repo files on confirm', () => {
      const file = makeRepoFile({ is_downloaded: true, installed_path: 'companion.safetensors' });
      component.deleteFile(file);
      expect(mockModelService.deleteModel).toHaveBeenCalledWith('loras', 'companion.safetensors');
      expect(mockNotifService.show).toHaveBeenCalledWith('success', expect.any(String));
      expect(mockModelService.getRepoFiles).toHaveBeenCalled();
    });

    it('does not navigate away even when deleting the currently viewed file', () => {
      component.modelPath = 'companion.safetensors';
      const file = makeRepoFile({ is_downloaded: true, installed_path: 'companion.safetensors' });
      component.deleteFile(file);
      expect(router.navigate).not.toHaveBeenCalled();
    });
  });

  describe('copyTriggerWords()', () => {
    let clipboardWriteText: ReturnType<typeof vi.fn>;
    let originalNavigator: typeof navigator;

    beforeEach(() => {
      originalNavigator = globalThis.navigator;
      clipboardWriteText = vi.fn();
      vi.stubGlobal('navigator', {
        clipboard: { writeText: clipboardWriteText },
      });
    });

    afterEach(() => {
      vi.stubGlobal('navigator', originalNavigator);
    });

    it('copies trigger words as comma-separated string', async () => {
      clipboardWriteText.mockResolvedValue(undefined);
      component.meta.set(makeMeta({ trigger_words: ['alpha', 'beta', 'gamma'] }));
      await component.copyTriggerWords();
      expect(clipboardWriteText).toHaveBeenCalledWith('alpha, beta, gamma');
    });

    it('shows success toast when clipboard write resolves', async () => {
      clipboardWriteText.mockResolvedValue(undefined);
      await component.copyTriggerWords();
      expect(mockNotifService.show).toHaveBeenCalledWith('success', 'Trigger words copied');
    });

    it('shows error toast when clipboard write rejects', async () => {
      clipboardWriteText.mockRejectedValue(new Error('denied'));
      await component.copyTriggerWords();
      expect(mockNotifService.show).toHaveBeenCalledWith('error', 'Could not copy trigger words');
    });
  });

  describe('downloadFile', () => {
    it('calls startDownload with correct arguments for root-level model', () => {
      component.modelPath = 'my-lora.safetensors';
      const file = makeRepoFile();
      component.downloadFile(file);
      expect(mockDownloadService.startDownload).toHaveBeenCalledWith(
        'https://civitai.com/api/download/models/99999?token=abc',
        'loras',
        'companion.safetensors',
        'civitai',
        '99999',
        '',
      );
    });

    it('extracts CivitAI version_id from download_url as source_id', () => {
      component.modelPath = 'my-lora.safetensors';
      component.downloadFile(
        makeRepoFile({ download_url: 'https://civitai.com/api/download/models/12345' }),
      );
      expect(mockDownloadService.startDownload).toHaveBeenCalledWith(
        expect.any(String),
        'loras',
        'companion.safetensors',
        'civitai',
        '12345',
        '',
      );
    });

    it('uses catalog entry source_page_id as source_id for huggingface', () => {
      component.meta.set(
        makeMeta({
          source_platform: 'huggingface',
          source_url: 'https://huggingface.co/user/repo',
        }),
      );
      component.catalogEntry.set({
        id: 1,
        source_platform: 'huggingface',
        source_page_id: 'user/repo',
        source_page_url: '',
        display_name: '',
        thumbnail_url: '',
        base_model: '',
        created_at: '',
        model_type: 'loras',
        is_empty: false,
        installed_files: [],
        repo_files: [],
        description: '',
        trigger_words: [],
        tags: [],
        media: [],
      });
      component.downloadFile(
        makeRepoFile({
          download_url: 'https://huggingface.co/user/repo/resolve/main/model.safetensors',
        }),
      );
      expect(mockDownloadService.startDownload).toHaveBeenCalledWith(
        expect.any(String),
        'loras',
        'companion.safetensors',
        'huggingface',
        'user/repo',
        '',
      );
    });

    it('prepends subfolder when model is in a subdirectory', () => {
      component.modelPath = 'sdxl/my-lora.safetensors';
      const file = makeRepoFile();
      component.downloadFile(file);
      expect(mockDownloadService.startDownload).toHaveBeenCalledWith(
        'https://civitai.com/api/download/models/99999?token=abc',
        'loras',
        'sdxl/companion.safetensors',
        'civitai',
        '99999',
        '',
      );
    });

    it('shows success notification on successful enqueue', () => {
      component.downloadFile(makeRepoFile());
      expect(mockNotifService.show).toHaveBeenCalledWith(
        'success',
        expect.stringContaining('companion.safetensors'),
      );
    });

    it('does nothing when download_url is empty', () => {
      component.downloadFile(makeRepoFile({ download_url: '' }));
      expect(mockDownloadService.startDownload).not.toHaveBeenCalled();
    });

    it('removes filename from downloadingFiles set on error', () => {
      mockDownloadService.startDownload.mockReturnValueOnce(throwError(() => new Error('fail')));
      const file = makeRepoFile();
      component.downloadFile(file);
      expect(component.downloadingFiles().has(file.filename)).toBe(false);
      expect(mockNotifService.show).toHaveBeenCalledWith('error', expect.any(String));
    });
  });
});
