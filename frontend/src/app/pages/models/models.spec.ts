import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { Models } from './models';
import { ModelFile, ModelService, CatalogEntry, CatalogListResponse } from '../../services/model';
import { WorkflowService } from '../../services/workflow';
import { SettingsService } from '../../services/settings';
import { NotificationService } from '../../services/notification';

// BroadcastChannel is not available in jsdom — stub it so `new` works correctly.
type MockChannel = {
  onmessage: ((ev: MessageEvent) => void) | null;
  close: ReturnType<typeof vi.fn>;
};
let capturedChannel: MockChannel | null = null;

vi.stubGlobal(
  'BroadcastChannel',
  vi.fn().mockImplementation(function MockBroadcastChannel() {
    capturedChannel = { onmessage: null, close: vi.fn() };
    return capturedChannel;
  }),
);

const emptyCatalog: CatalogListResponse = { entries: [], unknown_files: {} };

const mockModelService = {
  listCatalog: vi.fn(),
  deleteModel: vi.fn(),
  organizeIntoSubfolders: vi.fn(),
  getModelTypes: vi.fn(),
  moveModel: vi.fn(),
  getPendingQueue: vi.fn(),
};

const mockWorkflowService = {
  addToWorkflow: vi.fn(),
};

const mockSettingsService = {
  getOrganizeEnabled: vi.fn(),
};

const mockNotifService = { show: vi.fn() };

function findOrganizeButton(el: HTMLElement): HTMLButtonElement | undefined {
  return Array.from(el.querySelectorAll<HTMLButtonElement>('button')).find((b) =>
    b.textContent?.includes('Organize into subfolders'),
  );
}

async function createFixture() {
  const fixture = TestBed.createComponent(Models);
  fixture.detectChanges();
  await fixture.whenStable();
  return fixture;
}

async function getComponent() {
  return (await createFixture()).componentInstance;
}

function triggerMessage() {
  capturedChannel?.onmessage?.(new MessageEvent('message'));
}

describe('Models component', () => {
  beforeEach(async () => {
    capturedChannel = null;
    vi.clearAllMocks();
    mockModelService.listCatalog.mockReturnValue(of(emptyCatalog));
    mockModelService.getPendingQueue.mockReturnValue(of([]));
    mockSettingsService.getOrganizeEnabled.mockReturnValue(of(false));

    await TestBed.configureTestingModule({
      imports: [Models],
      providers: [
        provideRouter([]),
        { provide: ModelService, useValue: mockModelService },
        { provide: WorkflowService, useValue: mockWorkflowService },
        { provide: SettingsService, useValue: mockSettingsService },
        { provide: NotificationService, useValue: mockNotifService },
        provideTranslateServiceForTests(),
      ],
    }).compileComponents();
  });

  it('creates successfully', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('calls listCatalog on init', async () => {
    await createFixture();
    expect(mockModelService.listCatalog).toHaveBeenCalledTimes(1);
  });

  it('calls getOrganizeEnabled on init', async () => {
    await createFixture();
    expect(mockSettingsService.getOrganizeEnabled).toHaveBeenCalledTimes(1);
  });

  it('sets organizeEnabled to false when setting is off', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.organizeEnabled()).toBe(false);
  });

  it('sets organizeEnabled to true when setting is on', async () => {
    mockSettingsService.getOrganizeEnabled.mockReturnValue(of(true));
    const fixture = await createFixture();
    expect(fixture.componentInstance.organizeEnabled()).toBe(true);
  });

  it('hides organize button when setting is disabled', async () => {
    const fixture = await createFixture();
    expect(findOrganizeButton(fixture.nativeElement)).toBeUndefined();
  });

  it('shows organize button when setting is enabled', async () => {
    mockSettingsService.getOrganizeEnabled.mockReturnValue(of(true));
    const fixture = await createFixture();
    expect(findOrganizeButton(fixture.nativeElement)).toBeTruthy();
  });

  it('populates catalogEntries on successful load', async () => {
    const data: CatalogListResponse = {
      entries: [
        {
          id: 1,
          source_platform: 'civitai',
          source_page_id: '123',
          source_page_url: '',
          display_name: 'My Model',
          thumbnail_url: '',
          base_model: 'SDXL',
          created_at: '2024-01-01',
          model_type: 'loras',
          is_empty: false,
          installed_files: [],
        },
      ],
      unknown_files: {},
    };
    mockModelService.listCatalog.mockReturnValue(of(data));
    const fixture = await createFixture();
    expect(fixture.componentInstance.catalogEntries().length).toBe(1);
    expect(fixture.componentInstance.catalogEntries()[0].display_name).toBe('My Model');
  });

  it('sets error signal on load failure', async () => {
    mockModelService.listCatalog.mockReturnValue(throwError(() => new Error('network error')));
    const fixture = await createFixture();
    expect(fixture.componentInstance.error()).toBe('network error');
  });

  it('sets loading to false after successful load', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.loading()).toBe(false);
  });

  it('showEmpty defaults to false', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.showEmpty()).toBe(false);
  });

  it('empty entries are filtered out when showEmpty is false', async () => {
    const data: CatalogListResponse = {
      entries: [
        {
          id: 1,
          source_platform: 'civitai',
          source_page_id: '123',
          source_page_url: '',
          display_name: 'Empty Model',
          thumbnail_url: '',
          base_model: '',
          created_at: '2024-01-01',
          model_type: 'loras',
          is_empty: true,
          installed_files: [],
        },
      ],
      unknown_files: {},
    };
    mockModelService.listCatalog.mockReturnValue(of(data));
    const fixture = await createFixture();
    expect(fixture.componentInstance.filteredEntries().length).toBe(0);
  });

  it('empty entries appear when showEmpty is true', async () => {
    const data: CatalogListResponse = {
      entries: [
        {
          id: 1,
          source_platform: 'civitai',
          source_page_id: '123',
          source_page_url: '',
          display_name: 'Empty Model',
          thumbnail_url: '',
          base_model: '',
          created_at: '2024-01-01',
          model_type: 'loras',
          is_empty: true,
          installed_files: [],
        },
      ],
      unknown_files: {},
    };
    mockModelService.listCatalog.mockReturnValue(of(data));
    const fixture = await createFixture();
    fixture.componentInstance.showEmpty.set(true);
    expect(fixture.componentInstance.filteredEntries().length).toBe(1);
  });

  describe('cardTitle()', () => {
    it('returns display_name when set', async () => {
      const c = await getComponent();
      expect(
        c.cardTitle({
          id: 1,
          source_platform: 'civitai',
          source_page_id: '999',
          source_page_url: '',
          display_name: 'Awesome LoRA',
          thumbnail_url: '',
          base_model: '',
          created_at: '',
          model_type: 'loras',
          is_empty: false,
          installed_files: [],
        }),
      ).toBe('Awesome LoRA');
    });

    it('derives name from first installed filename when display_name empty', async () => {
      const c = await getComponent();
      expect(
        c.cardTitle({
          id: 2,
          source_platform: 'civitai',
          source_page_id: '999',
          source_page_url: '',
          display_name: '',
          thumbnail_url: '',
          base_model: '',
          created_at: '',
          model_type: 'loras',
          is_empty: false,
          installed_files: [
            {
              filename: 'sdxl/my-cool_lora.safetensors',
              model_type: 'loras',
              size_bytes: 0,
              modified_at: 0,
            },
          ],
        }),
      ).toBe('my cool lora');
    });

    it('uses last segment of HuggingFace source_page_id as fallback', async () => {
      const c = await getComponent();
      expect(
        c.cardTitle({
          id: 3,
          source_platform: 'huggingface',
          source_page_id: 'Keltezaa/BonnieWright',
          source_page_url: '',
          display_name: '',
          thumbnail_url: '',
          base_model: '',
          created_at: '',
          model_type: 'loras',
          is_empty: true,
          installed_files: [],
        }),
      ).toBe('BonnieWright');
    });

    it('falls back to source_page_id for CivitAI without files', async () => {
      const c = await getComponent();
      expect(
        c.cardTitle({
          id: 4,
          source_platform: 'civitai',
          source_page_id: '12345',
          source_page_url: '',
          display_name: '',
          thumbnail_url: '',
          base_model: '',
          created_at: '',
          model_type: 'loras',
          is_empty: true,
          installed_files: [],
        }),
      ).toBe('12345');
    });
  });

  describe('cardDetailRoute() and cardDetailQuery()', () => {
    it('routes non-empty catalog entry to catalog-detail with pageId', async () => {
      const c = await getComponent();
      const entry = {
        id: 1,
        source_platform: 'civitai',
        source_page_id: '123',
        source_page_url: '',
        display_name: 'Test',
        thumbnail_url: '',
        base_model: '',
        created_at: '',
        model_type: 'loras',
        is_empty: false,
        installed_files: [
          { filename: 'my.safetensors', model_type: 'loras', size_bytes: 0, modified_at: 0 },
        ],
      };
      expect(c.cardDetailRoute(entry)).toEqual(['/catalog', 'civitai']);
      expect(c.cardDetailQuery(entry)).toEqual({ pageId: '123' });
    });

    it('routes empty entry to catalog-detail with queryParams', async () => {
      const c = await getComponent();
      const entry = {
        id: 2,
        source_platform: 'huggingface',
        source_page_id: 'user/repo',
        source_page_url: '',
        display_name: '',
        thumbnail_url: '',
        base_model: '',
        created_at: '',
        model_type: 'loras',
        is_empty: true,
        installed_files: [],
      };
      expect(c.cardDetailRoute(entry)).toEqual(['/catalog', 'huggingface']);
      expect(c.cardDetailQuery(entry)).toEqual({ pageId: 'user/repo' });
    });
  });

  describe('copyTriggerWords()', () => {
    let clipboardWriteText: ReturnType<typeof vi.fn>;
    let originalNavigator: typeof navigator;

    const makeEntry = (overrides: Partial<CatalogEntry> = {}): CatalogEntry => ({
      id: 1,
      source_platform: 'civitai',
      source_page_id: '1',
      source_page_url: '',
      display_name: 'Test',
      thumbnail_url: '',
      base_model: '',
      created_at: '',
      model_type: 'loras',
      is_empty: false,
      is_video_only: false,
      installed_files: [],
      trigger_words: ['word1', 'word2'],
      ...overrides,
    });

    beforeEach(() => {
      originalNavigator = globalThis.navigator;
      clipboardWriteText = vi.fn().mockResolvedValue(undefined);
      vi.stubGlobal('navigator', { clipboard: { writeText: clipboardWriteText } });
    });

    afterEach(() => {
      vi.stubGlobal('navigator', originalNavigator);
    });

    it('copies trigger words as comma-separated string', async () => {
      const c = await getComponent();
      await c.copyTriggerWords(makeEntry({ trigger_words: ['word1', 'word2'] }));
      expect(clipboardWriteText).toHaveBeenCalledWith('word1, word2');
    });

    it('shows success toast after copying', async () => {
      const c = await getComponent();
      await c.copyTriggerWords(makeEntry());
      expect(mockNotifService.show).toHaveBeenCalledWith('success', 'Trigger words copied');
    });

    it('shows error toast when clipboard rejects', async () => {
      clipboardWriteText.mockRejectedValue(new Error('denied'));
      const c = await getComponent();
      await c.copyTriggerWords(makeEntry());
      expect(mockNotifService.show).toHaveBeenCalledWith('error', 'Could not copy trigger words');
    });

    it('copies empty string when trigger_words is undefined', async () => {
      const c = await getComponent();
      await c.copyTriggerWords(makeEntry({ trigger_words: undefined }));
      expect(clipboardWriteText).toHaveBeenCalledWith('');
    });
  });

  describe('filteredEntries() — base model filter', () => {
    const makeEntry = (overrides: Partial<CatalogEntry>): CatalogEntry => ({
      id: 1,
      source_platform: 'civitai',
      source_page_id: '1',
      source_page_url: '',
      display_name: 'A',
      thumbnail_url: '',
      base_model: 'SDXL',
      created_at: '2024-01-01',
      model_type: 'loras',
      is_empty: false,
      is_video_only: false,
      installed_files: [],
      ...overrides,
    });

    it('filters out entries without a base_model when UNKNOWN_BASE_MODEL is selected', async () => {
      const entries: CatalogEntry[] = [
        makeEntry({ id: 1, base_model: 'SDXL' }),
        makeEntry({ id: 2, base_model: '' }),
      ];
      mockModelService.listCatalog.mockReturnValue(of({ entries, unknown_files: {} }));
      const fixture = await createFixture();
      fixture.componentInstance.baseModelFilter.set('__unknown__');
      expect(fixture.componentInstance.filteredEntries().length).toBe(1);
      expect(fixture.componentInstance.filteredEntries()[0].id).toBe(2);
    });

    it('filters by specific base model', async () => {
      const entries: CatalogEntry[] = [
        makeEntry({ id: 1, base_model: 'SDXL' }),
        makeEntry({ id: 2, base_model: 'Pony' }),
      ];
      mockModelService.listCatalog.mockReturnValue(of({ entries, unknown_files: {} }));
      const fixture = await createFixture();
      fixture.componentInstance.baseModelFilter.set('Pony');
      expect(fixture.componentInstance.filteredEntries().length).toBe(1);
      expect(fixture.componentInstance.filteredEntries()[0].id).toBe(2);
    });

    it('filters out entries without a source_platform when UNKNOWN_SOURCE is selected', async () => {
      const entries: CatalogEntry[] = [
        makeEntry({ id: 1, source_platform: 'civitai' }),
        makeEntry({ id: 2, source_platform: '' }),
      ];
      mockModelService.listCatalog.mockReturnValue(of({ entries, unknown_files: {} }));
      const fixture = await createFixture();
      fixture.componentInstance.sourceFilter.set('__unknown_source__');
      expect(fixture.componentInstance.filteredEntries().length).toBe(1);
      expect(fixture.componentInstance.filteredEntries()[0].id).toBe(2);
    });

    it('filters by specific source platform', async () => {
      const entries: CatalogEntry[] = [
        makeEntry({ id: 1, source_platform: 'civitai' }),
        makeEntry({ id: 2, source_platform: 'huggingface' }),
      ];
      mockModelService.listCatalog.mockReturnValue(of({ entries, unknown_files: {} }));
      const fixture = await createFixture();
      fixture.componentInstance.sourceFilter.set('huggingface');
      expect(fixture.componentInstance.filteredEntries().length).toBe(1);
      expect(fixture.componentInstance.filteredEntries()[0].id).toBe(2);
    });

    it('sorts by name-asc', async () => {
      const entries: CatalogEntry[] = [
        makeEntry({ id: 1, display_name: 'Zebra' }),
        makeEntry({ id: 2, display_name: 'Alpha' }),
      ];
      mockModelService.listCatalog.mockReturnValue(of({ entries, unknown_files: {} }));
      const fixture = await createFixture();
      fixture.componentInstance.sortBy.set('name-asc');
      const result = fixture.componentInstance.filteredEntries();
      expect(result[0].display_name).toBe('Alpha');
      expect(result[1].display_name).toBe('Zebra');
    });

    it('sorts by name-desc', async () => {
      const entries: CatalogEntry[] = [
        makeEntry({ id: 1, display_name: 'Alpha' }),
        makeEntry({ id: 2, display_name: 'Zebra' }),
      ];
      mockModelService.listCatalog.mockReturnValue(of({ entries, unknown_files: {} }));
      const fixture = await createFixture();
      fixture.componentInstance.sortBy.set('name-desc');
      const result = fixture.componentInstance.filteredEntries();
      expect(result[0].display_name).toBe('Zebra');
      expect(result[1].display_name).toBe('Alpha');
    });

    it('sorts by created-desc (newest first)', async () => {
      const entries: CatalogEntry[] = [
        makeEntry({ id: 1, display_name: 'Old', created_at: '2020-01-01' }),
        makeEntry({ id: 2, display_name: 'New', created_at: '2024-01-01' }),
      ];
      mockModelService.listCatalog.mockReturnValue(of({ entries, unknown_files: {} }));
      const fixture = await createFixture();
      fixture.componentInstance.sortBy.set('created-desc');
      const result = fixture.componentInstance.filteredEntries();
      expect(result[0].display_name).toBe('New');
    });

    it('sorts by created-asc (oldest first)', async () => {
      const entries: CatalogEntry[] = [
        makeEntry({ id: 1, display_name: 'New', created_at: '2024-01-01' }),
        makeEntry({ id: 2, display_name: 'Old', created_at: '2020-01-01' }),
      ];
      mockModelService.listCatalog.mockReturnValue(of({ entries, unknown_files: {} }));
      const fixture = await createFixture();
      fixture.componentInstance.sortBy.set('created-asc');
      const result = fixture.componentInstance.filteredEntries();
      expect(result[0].display_name).toBe('Old');
    });
  });

  describe('clearAllFilters()', () => {
    it('resets all filter signals to defaults', async () => {
      const c = await getComponent();
      c.baseModelFilter.set('SDXL');
      c.formatFilter.set('safetensors');
      c.sourceFilter.set('civitai');
      c.tagFilter.set(['anime']);
      c.tagInput.set('searching');
      c.clearAllFilters();
      expect(c.baseModelFilter()).toBe('');
      expect(c.formatFilter()).toBe('');
      expect(c.sourceFilter()).toBe('');
      expect(c.tagFilter()).toEqual([]);
      expect(c.tagInput()).toBe('');
    });
  });

  describe('isPending()', () => {
    it('returns true when filename is in pendingFilenames', async () => {
      const c = await getComponent();
      c.pendingFilenames.set(new Set(['models/my-lora.safetensors']));
      expect(c.isPending('models/my-lora.safetensors')).toBe(true);
    });

    it('returns false when filename is not in pendingFilenames', async () => {
      const c = await getComponent();
      c.pendingFilenames.set(new Set());
      expect(c.isPending('models/my-lora.safetensors')).toBe(false);
    });
  });

  describe('basename()', () => {
    it('extracts last path segment', async () => {
      const c = await getComponent();
      expect(c.basename('loras/sub/my-model.safetensors')).toBe('my-model.safetensors');
    });

    it('returns whole string for no-slash path', async () => {
      const c = await getComponent();
      expect(c.basename('model.safetensors')).toBe('model.safetensors');
    });
  });

  describe('cardDetailRoute() fallback branches', () => {
    it('routes to model-type page when entry has no source but has installed file', async () => {
      const c = await getComponent();
      const entry: CatalogEntry = {
        id: 5,
        source_platform: '',
        source_page_id: '',
        source_page_url: '',
        display_name: 'Local Model',
        thumbnail_url: '',
        base_model: '',
        created_at: '',
        model_type: 'loras',
        is_empty: false,
        installed_files: [
          {
            filename: 'loras/local.safetensors',
            model_type: 'loras',
            size_bytes: 0,
            modified_at: 0,
          },
        ],
      };
      expect(c.cardDetailRoute(entry)).toEqual(['/models', 'loras', 'loras/local.safetensors']);
    });

    it('falls back to /catalog when entry has no source and no installed files', async () => {
      const c = await getComponent();
      const entry: CatalogEntry = {
        id: 6,
        source_platform: '',
        source_page_id: '',
        source_page_url: '',
        display_name: '',
        thumbnail_url: '',
        base_model: '',
        created_at: '',
        model_type: 'loras',
        is_empty: true,
        installed_files: [],
      };
      expect(c.cardDetailRoute(entry)).toEqual(['/catalog']);
    });
  });

  describe('cardDetailQuery() null case', () => {
    it('returns null when entry has no source platform', async () => {
      const c = await getComponent();
      const entry: CatalogEntry = {
        id: 7,
        source_platform: '',
        source_page_id: '',
        source_page_url: '',
        display_name: '',
        thumbnail_url: '',
        base_model: '',
        created_at: '',
        model_type: 'loras',
        is_empty: true,
        installed_files: [],
      };
      expect(c.cardDetailQuery(entry)).toBeNull();
    });
  });

  describe('catalogThumbnailUrl()', () => {
    it('returns null for empty thumbnail_url', async () => {
      const c = await getComponent();
      const entry: CatalogEntry = {
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
      };
      expect(c.catalogThumbnailUrl(entry)).toBeNull();
    });

    it('returns mediaUrl result for non-empty thumbnail_url', async () => {
      const c = await getComponent();
      const entry: CatalogEntry = {
        id: 1,
        source_platform: 'civitai',
        source_page_id: '1',
        source_page_url: '',
        display_name: '',
        thumbnail_url: '/media/thumb.jpg',
        base_model: '',
        created_at: '',
        model_type: 'loras',
        is_empty: false,
        installed_files: [],
      };
      expect(c.catalogThumbnailUrl(entry)).toContain('thumb.jpg');
    });
  });

  describe('unknownThumbnailUrl()', () => {
    it('returns null when meta has no media', async () => {
      const c = await getComponent();
      expect(
        c.unknownThumbnailUrl({
          description: '',
          trigger_words: [],
          tags: [],
          media: [],
          base_model: '',
          source_platform: '',
          source_url: '',
          size_bytes: 0,
        }),
      ).toBeNull();
    });

    it('returns mediaUrl for first image media item', async () => {
      const c = await getComponent();
      const meta = {
        description: '',
        trigger_words: [],
        tags: [],
        media: [{ id: 1, media_type: 'image', local_path: '/m/preview.jpg' }],
        base_model: '',
        source_platform: '',
        source_url: '',
        size_bytes: 0,
      };
      expect(c.unknownThumbnailUrl(meta)).toContain('preview.jpg');
    });

    it('returns null when meta is undefined', async () => {
      const c = await getComponent();
      expect(c.unknownThumbnailUrl(undefined)).toBeNull();
    });
  });

  describe('addToWorkflow()', () => {
    it('shows success notification after enqueueing', async () => {
      mockWorkflowService.addToWorkflow.mockReturnValue(of({}));
      const c = await getComponent();
      c.addToWorkflow('loras', 'my-lora.safetensors');
      expect(mockNotifService.show).toHaveBeenCalledWith(
        'success',
        expect.stringContaining('queued'),
      );
    });

    it('adds filename to queuedForWorkflow on success', async () => {
      mockWorkflowService.addToWorkflow.mockReturnValue(of({}));
      const c = await getComponent();
      c.addToWorkflow('loras', 'my-lora.safetensors');
      expect(c.queuedForWorkflow().has('my-lora.safetensors')).toBe(true);
    });

    it('shows error notification when enqueueing fails', async () => {
      mockWorkflowService.addToWorkflow.mockReturnValue(throwError(() => new Error('fail')));
      const c = await getComponent();
      c.addToWorkflow('loras', 'my-lora.safetensors');
      expect(mockNotifService.show).toHaveBeenCalledWith('error', expect.any(String));
    });
  });

  describe('deleteUnknownModel()', () => {
    const makeModelFile = (overrides: Partial<ModelFile> = {}): ModelFile => ({
      filename: 'loras/my-lora.safetensors',
      base_dir: 'loras',
      size_bytes: 1024,
      modified_at: 0,
      ...overrides,
    });

    it('shows success notification and reloads after delete', async () => {
      mockModelService.deleteModel.mockReturnValue(of(undefined));
      const c = await getComponent();
      const callsBefore = mockModelService.listCatalog.mock.calls.length;
      c.deleteUnknownModel('loras', makeModelFile());
      expect(mockNotifService.show).toHaveBeenCalledWith('success', expect.any(String));
      expect(mockModelService.listCatalog.mock.calls.length).toBeGreaterThan(callsBefore);
    });

    it('shows error notification on delete failure', async () => {
      mockModelService.deleteModel.mockReturnValue(throwError(() => new Error('disk full')));
      const c = await getComponent();
      c.deleteUnknownModel('loras', makeModelFile());
      expect(mockNotifService.show).toHaveBeenCalledWith(
        'error',
        expect.stringContaining('disk full'),
      );
    });
  });

  describe('BroadcastChannel tmm message', () => {
    it('checks pending queue immediately when message arrives', async () => {
      await createFixture();
      const prevCalls = mockModelService.getPendingQueue.mock.calls.length;
      triggerMessage();
      expect(mockModelService.getPendingQueue).toHaveBeenCalledTimes(prevCalls + 1);
    });

    it('does not call listCatalog directly when message arrives with empty queue', async () => {
      await createFixture();
      expect(mockModelService.listCatalog).toHaveBeenCalledTimes(1);
      triggerMessage();
      expect(mockModelService.listCatalog).toHaveBeenCalledTimes(1);
    });

    it('re-fetches organize setting when message arrives', async () => {
      await createFixture();
      expect(mockSettingsService.getOrganizeEnabled).toHaveBeenCalledTimes(1);
      triggerMessage();
      expect(mockSettingsService.getOrganizeEnabled).toHaveBeenCalledTimes(2);
    });

    it('closes the channel on component destroy', async () => {
      await createFixture();
      const channel = capturedChannel!;
      TestBed.resetTestingModule();
      expect(channel.close).toHaveBeenCalled();
    });
  });
});
