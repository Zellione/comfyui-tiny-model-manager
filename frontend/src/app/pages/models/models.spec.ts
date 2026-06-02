import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { Models } from './models';
import { ModelService, CatalogListResponse } from '../../services/model';
import { WorkflowService } from '../../services/workflow';
import { SettingsService } from '../../services/settings';

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

function findOrganizeButton(el: HTMLElement): HTMLButtonElement | undefined {
  return Array.from(el.querySelectorAll<HTMLButtonElement>('button')).find((b) =>
    b.textContent?.includes('Organize into subfolders'),
  );
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
      ],
    }).compileComponents();
  });

  async function createFixture() {
    const fixture = TestBed.createComponent(Models);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

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

  describe('BroadcastChannel tmm message', () => {
    function triggerMessage() {
      capturedChannel?.onmessage?.(new MessageEvent('message'));
    }

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
