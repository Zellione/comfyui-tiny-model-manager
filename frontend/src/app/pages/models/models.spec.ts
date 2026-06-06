import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { Models } from './models';
import { ModelService, CatalogEntry, CatalogListResponse } from '../../services/model';
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
