import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { Models } from './models';
import { ModelService } from '../../services/model';
import { WorkflowService } from '../../services/workflow';
import { SettingsService } from '../../services/settings';

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

  describe('tmm:settings-changed event', () => {
    it('calls listModels again when event fires', async () => {
      await createFixture();
      expect(mockModelService.listModels).toHaveBeenCalledTimes(1);

      window.dispatchEvent(new CustomEvent('tmm:settings-changed'));

      expect(mockModelService.listModels).toHaveBeenCalledTimes(2);
    });

    it('re-fetches organize setting when event fires', async () => {
      await createFixture();
      expect(mockSettingsService.getOrganizeEnabled).toHaveBeenCalledTimes(1);

      window.dispatchEvent(new CustomEvent('tmm:settings-changed'));

      expect(mockSettingsService.getOrganizeEnabled).toHaveBeenCalledTimes(2);
    });

    it('updates organizeEnabled when event fires with changed setting', async () => {
      const fixture = await createFixture();
      expect(fixture.componentInstance.organizeEnabled()).toBe(false);

      mockSettingsService.getOrganizeEnabled.mockReturnValue(of(true));
      window.dispatchEvent(new CustomEvent('tmm:settings-changed'));
      fixture.detectChanges();

      expect(fixture.componentInstance.organizeEnabled()).toBe(true);
    });

    it('does not fire listModels after component is destroyed', async () => {
      await createFixture();
      expect(mockModelService.listModels).toHaveBeenCalledTimes(1);

      TestBed.resetTestingModule();
      window.dispatchEvent(new CustomEvent('tmm:settings-changed'));

      expect(mockModelService.listModels).toHaveBeenCalledTimes(1);
    });
  });
});
