import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { Models } from './models';
import { ModelService } from '../../services/model';
import { WorkflowService } from '../../services/workflow';
import { SettingsService } from '../../services/settings';

// BroadcastChannel is not available in jsdom — stub it so `new` works correctly.
// Returning a plain object from the implementation becomes the result of `new`.
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

const emptyModels = {};

const mockModelService = {
  listModels: vi.fn(),
  deleteModel: vi.fn(),
  organizeIntoSubfolders: vi.fn(),
  getModelTypes: vi.fn(),
  moveModel: vi.fn(),
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
    mockModelService.listModels.mockReturnValue(of(emptyModels));
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

  it('calls listModels on init', async () => {
    await createFixture();
    expect(mockModelService.listModels).toHaveBeenCalledTimes(1);
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

  it('populates modelsByType on successful load', async () => {
    const data = {
      loras: [{ filename: 'a.safetensors', base_dir: '/m', size_bytes: 1, modified_at: 0 }],
    };
    mockModelService.listModels.mockReturnValue(of(data));
    const fixture = await createFixture();
    expect(fixture.componentInstance.modelsByType()).toEqual(data);
  });

  it('sets error signal on load failure', async () => {
    mockModelService.listModels.mockReturnValue(throwError(() => new Error('network error')));
    const fixture = await createFixture();
    expect(fixture.componentInstance.error()).toBe('network error');
  });

  it('sets loading to false after successful load', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.loading()).toBe(false);
  });

  describe('BroadcastChannel tmm message', () => {
    function triggerMessage() {
      capturedChannel?.onmessage?.(new MessageEvent('message'));
    }

    it('calls listModels again when message arrives', async () => {
      await createFixture();
      expect(mockModelService.listModels).toHaveBeenCalledTimes(1);

      triggerMessage();

      expect(mockModelService.listModels).toHaveBeenCalledTimes(2);
    });

    it('re-fetches organize setting when message arrives', async () => {
      await createFixture();
      expect(mockSettingsService.getOrganizeEnabled).toHaveBeenCalledTimes(1);

      triggerMessage();

      expect(mockSettingsService.getOrganizeEnabled).toHaveBeenCalledTimes(2);
    });

    it('updates organizeEnabled when message arrives with changed setting', async () => {
      const fixture = await createFixture();
      expect(fixture.componentInstance.organizeEnabled()).toBe(false);

      mockSettingsService.getOrganizeEnabled.mockReturnValue(of(true));
      triggerMessage();
      fixture.detectChanges();

      expect(fixture.componentInstance.organizeEnabled()).toBe(true);
    });

    it('closes the channel on component destroy', async () => {
      await createFixture();
      const channel = capturedChannel!;

      TestBed.resetTestingModule();

      expect(channel.close).toHaveBeenCalled();
    });
  });
});
