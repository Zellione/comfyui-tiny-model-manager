import { TestBed } from '@angular/core/testing';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { Settings } from './settings';
import { KeywordsService } from '../../services/keywords';
import { NotificationService } from '../../services/notification';
import { SettingsService } from '../../services/settings';
import { FilenameKeyword } from '../../utils/filename-detector';

const mockKeywordsService = {
  getKeywords: vi.fn(),
  createKeyword: vi.fn(),
  updateKeyword: vi.fn(),
  deleteKeyword: vi.fn(),
};

const mockNotifService = {
  show: vi.fn(),
};

const mockSettingsService = {
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
};

function makeKw(id: number): FilenameKeyword {
  return {
    id,
    keyword: `kw${id}`,
    base_model: 'SDXL 1.0',
    model_type: 'loras',
    sort_order: id * 10,
  };
}

async function configureTestBed() {
  await TestBed.configureTestingModule({
    imports: [Settings],
    providers: [
      { provide: KeywordsService, useValue: mockKeywordsService },
      { provide: NotificationService, useValue: mockNotifService },
      { provide: SettingsService, useValue: mockSettingsService },
      provideTranslateServiceForTests(),
    ],
  }).compileComponents();
}

async function createFixture() {
  const fixture = TestBed.createComponent(Settings);
  fixture.detectChanges();
  await fixture.whenStable();
  return fixture;
}

describe('Settings component', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockKeywordsService.getKeywords.mockReturnValue(of([]));
    mockSettingsService.getSettings.mockReturnValue(of({ missing_models_integration: true }));
    mockSettingsService.updateSettings.mockReturnValue(of(undefined));
    await configureTestBed();
  });

  describe('missing models integration toggle', () => {
    it('loads the current value', async () => {
      mockSettingsService.getSettings.mockReturnValue(of({ missing_models_integration: false }));
      const comp = (await createFixture()).componentInstance;
      expect(comp.missingModelsIntegration()).toBe(false);
      expect(comp.integrationLoading()).toBe(false);
    });

    it('defaults to enabled when the key is absent', async () => {
      mockSettingsService.getSettings.mockReturnValue(of({}));
      const comp = (await createFixture()).componentInstance;
      expect(comp.missingModelsIntegration()).toBe(true);
    });

    it('stops loading when the request fails', async () => {
      mockSettingsService.getSettings.mockReturnValue(throwError(() => new Error('nope')));
      const comp = (await createFixture()).componentInstance;
      expect(comp.integrationLoading()).toBe(false);
    });

    it('persists a change', async () => {
      const comp = (await createFixture()).componentInstance;
      comp.setMissingModelsIntegration(false);
      expect(mockSettingsService.updateSettings).toHaveBeenCalledWith({
        missing_models_integration: false,
      });
      expect(comp.missingModelsIntegration()).toBe(false);
    });

    it('reverts and notifies when saving fails', async () => {
      mockSettingsService.updateSettings.mockReturnValue(throwError(() => new Error('nope')));
      const comp = (await createFixture()).componentInstance;
      comp.setMissingModelsIntegration(false);
      expect(comp.missingModelsIntegration()).toBe(true);
      expect(mockNotifService.show).toHaveBeenCalledWith('error', expect.any(String));
    });
  });

  describe('ngOnInit / load', () => {
    it('sets keywords and clears loading on success', async () => {
      const kws = [makeKw(1), makeKw(2)];
      mockKeywordsService.getKeywords.mockReturnValue(of(kws));
      const fixture = await createFixture();
      const comp = fixture.componentInstance;
      expect(comp.keywords()).toEqual(kws);
      expect(comp.loading()).toBe(false);
      expect(comp.error()).toBe('');
    });

    it('sets error message and clears loading on failure', async () => {
      mockKeywordsService.getKeywords.mockReturnValue(throwError(() => new Error('net')));
      const fixture = await createFixture();
      const comp = fixture.componentInstance;
      expect(comp.error()).toBe('Failed to load keywords');
      expect(comp.loading()).toBe(false);
    });
  });

  describe('startEdit', () => {
    it('populates edit signals from the keyword', async () => {
      const fixture = await createFixture();
      const comp = fixture.componentInstance;
      comp.startEdit(makeKw(42));
      expect(comp.editingId()).toBe(42);
      expect(comp.editKeyword()).toBe('kw42');
      expect(comp.editBaseModel()).toBe('SDXL 1.0');
      expect(comp.editModelType()).toBe('loras');
    });

    it('uses empty string for null base_model and model_type', async () => {
      const fixture = await createFixture();
      const comp = fixture.componentInstance;
      comp.startEdit({ id: 7, keyword: 'flux', base_model: null, model_type: null, sort_order: 0 });
      expect(comp.editBaseModel()).toBe('');
      expect(comp.editModelType()).toBe('');
    });
  });

  describe('cancelEdit', () => {
    it('resets editingId to null', async () => {
      const fixture = await createFixture();
      const comp = fixture.componentInstance;
      comp.startEdit(makeKw(1));
      comp.cancelEdit();
      expect(comp.editingId()).toBeNull();
    });
  });

  describe('saveEdit', () => {
    it('does nothing when editingId is null', async () => {
      const fixture = await createFixture();
      const comp = fixture.componentInstance;
      comp.saveEdit();
      expect(mockKeywordsService.updateKeyword).not.toHaveBeenCalled();
    });

    it('does nothing when editKeyword is blank', async () => {
      const fixture = await createFixture();
      const comp = fixture.componentInstance;
      comp.startEdit(makeKw(1));
      comp.editKeyword.set('   ');
      comp.saveEdit();
      expect(mockKeywordsService.updateKeyword).not.toHaveBeenCalled();
    });

    it('calls updateKeyword and reloads on success', async () => {
      mockKeywordsService.updateKeyword.mockReturnValue(of(undefined));
      const fixture = await createFixture();
      const comp = fixture.componentInstance;
      comp.startEdit(makeKw(3));
      comp.saveEdit();
      expect(mockKeywordsService.updateKeyword).toHaveBeenCalledWith(3, 'kw3', 'SDXL 1.0', 'loras');
      expect(comp.editingId()).toBeNull();
      expect(comp.saving()).toBe(false);
    });

    it('shows error notification when updateKeyword fails', async () => {
      mockKeywordsService.updateKeyword.mockReturnValue(throwError(() => new Error()));
      const fixture = await createFixture();
      const comp = fixture.componentInstance;
      comp.startEdit(makeKw(1));
      comp.saveEdit();
      expect(mockNotifService.show).toHaveBeenCalledWith('error', 'Failed to save keyword');
      expect(comp.saving()).toBe(false);
    });
  });

  describe('addKeyword', () => {
    it('does nothing when newKeyword is empty', async () => {
      const fixture = await createFixture();
      fixture.componentInstance.addKeyword();
      expect(mockKeywordsService.createKeyword).not.toHaveBeenCalled();
    });

    it('calls createKeyword with trimmed values and reloads on success', async () => {
      mockKeywordsService.createKeyword.mockReturnValue(of({ id: 99 }));
      const fixture = await createFixture();
      const comp = fixture.componentInstance;
      comp.newKeyword.set('mykw');
      comp.newBaseModel.set('SD 1.5');
      comp.newModelType.set('loras');
      comp.addKeyword();
      expect(mockKeywordsService.createKeyword).toHaveBeenCalledWith('mykw', 'SD 1.5', 'loras');
      expect(comp.newKeyword()).toBe('');
      expect(comp.newBaseModel()).toBe('');
      expect(comp.newModelType()).toBe('');
      expect(comp.adding()).toBe(false);
    });

    it('passes null for blank base_model and model_type', async () => {
      mockKeywordsService.createKeyword.mockReturnValue(of({ id: 10 }));
      const fixture = await createFixture();
      const comp = fixture.componentInstance;
      comp.newKeyword.set('plain');
      comp.newBaseModel.set('  ');
      comp.newModelType.set('');
      comp.addKeyword();
      expect(mockKeywordsService.createKeyword).toHaveBeenCalledWith('plain', null, null);
    });

    it('shows error notification when createKeyword fails', async () => {
      mockKeywordsService.createKeyword.mockReturnValue(throwError(() => new Error()));
      const fixture = await createFixture();
      const comp = fixture.componentInstance;
      comp.newKeyword.set('fail-kw');
      comp.addKeyword();
      expect(mockNotifService.show).toHaveBeenCalledWith('error', 'Failed to add keyword');
      expect(comp.adding()).toBe(false);
    });
  });

  describe('deleteKeyword', () => {
    it('reloads after successful delete', async () => {
      const afterDelete = [makeKw(2)];
      mockKeywordsService.deleteKeyword.mockReturnValue(of(undefined));
      mockKeywordsService.getKeywords
        .mockReturnValueOnce(of([makeKw(1), makeKw(2)]))
        .mockReturnValueOnce(of(afterDelete));
      const fixture = await createFixture();
      const comp = fixture.componentInstance;
      comp.deleteKeyword(1);
      expect(comp.keywords()).toEqual(afterDelete);
    });

    it('shows error notification when deleteKeyword fails', async () => {
      mockKeywordsService.deleteKeyword.mockReturnValue(throwError(() => new Error()));
      const fixture = await createFixture();
      fixture.componentInstance.deleteKeyword(99);
      expect(mockNotifService.show).toHaveBeenCalledWith('error', 'Failed to delete keyword');
    });
  });
});
