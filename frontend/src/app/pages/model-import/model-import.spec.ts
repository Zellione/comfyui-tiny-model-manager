import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideLocationMocks } from '@angular/common/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { ModelImport } from './model-import';
import { ModelImportService, ImportJobState } from '../../services/model-import';
import { SettingsService } from '../../services/settings';

function jobState(over: Partial<ImportJobState> = {}): ImportJobState {
  return {
    id: 'j1',
    kind: 'scan',
    source_root: '/src/models',
    state: 'done',
    progress: 100,
    error: '',
    files: [],
    imported: [],
    skipped: [],
    failed: [],
    ...over,
  };
}

describe('ModelImport', () => {
  let fixture: ComponentFixture<ModelImport>;
  let component: ModelImport;
  let importService: {
    startScan: ReturnType<typeof vi.fn>;
    pollScan: ReturnType<typeof vi.fn>;
    startImport: ReturnType<typeof vi.fn>;
    pollJob: ReturnType<typeof vi.fn>;
    cancelJob: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    importService = {
      startScan: vi.fn().mockReturnValue(of({ job_id: 'j1', source_root: '/src/models' })),
      pollScan: vi.fn().mockReturnValue(of(jobState())),
      startImport: vi.fn().mockReturnValue(of({ job_id: 'j2' })),
      pollJob: vi.fn().mockReturnValue(of(jobState({ kind: 'import' }))),
      cancelJob: vi.fn().mockReturnValue(of({ cancelled: true })),
    };

    await TestBed.configureTestingModule({
      imports: [ModelImport],
      providers: [
        { provide: ModelImportService, useValue: importService },
        {
          provide: SettingsService,
          useValue: {
            getSettings: vi.fn().mockReturnValue(of({ import_source_root: '/remembered' })),
            updateSettings: vi.fn().mockReturnValue(of(undefined)),
          },
        },
        provideTranslateServiceForTests(),
        provideRouter([]),
        provideLocationMocks(),
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ModelImport);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('prefills the remembered source path', () => {
    expect(component.sourcePath()).toBe('/remembered');
  });

  it('starts a scan and stores the resolved root', async () => {
    component.sourcePath.set('/src');
    component.scan();
    await Promise.resolve();
    expect(importService.startScan).toHaveBeenCalledWith('/src');
    expect(component.sourceRoot()).toBe('/src/models');
  });

  it('surfaces a backend error key', async () => {
    importService.startScan.mockReturnValue(
      throwError(() => ({ error: { error: 'path_not_found' } })),
    );
    component.sourcePath.set('/gone');
    component.scan();
    await Promise.resolve();
    expect(component.errorKey()).toBe('import.errors.path_not_found');
  });

  it('falls back to a generic error key for an unknown failure', async () => {
    importService.startScan.mockReturnValue(throwError(() => ({ status: 500 })));
    component.scan();
    await Promise.resolve();
    expect(component.errorKey()).toBe('import.errors.generic');
  });

  it('groups scanned files by model type', () => {
    component.applyScanState(
      jobState({
        files: [
          { model_type: 'loras', filename: 'a', size_bytes: 1, status: 'new', file_hash: 'a' },
          { model_type: 'loras', filename: 'b', size_bytes: 2, status: 'new', file_hash: 'b' },
          {
            model_type: 'checkpoints',
            filename: 'c',
            size_bytes: 3,
            status: 'installed',
            file_hash: 'c',
          },
        ],
      }),
    );
    expect(component.groups().map((g) => g.modelType)).toEqual(['checkpoints', 'loras']);
    expect(component.groups()[1].files.length).toBe(2);
  });

  it('only counts selectable new files in select-all', () => {
    component.applyScanState(
      jobState({
        files: [
          { model_type: 'loras', filename: 'a', size_bytes: 1, status: 'new', file_hash: 'a' },
          {
            model_type: 'loras',
            filename: 'b',
            size_bytes: 2,
            status: 'installed',
            file_hash: 'b',
          },
        ],
      }),
    );
    component.toggleGroup('loras', true);
    expect(component.selectedCount()).toBe(1);
  });

  it('sends only the selected files to the import', async () => {
    component.applyScanState(
      jobState({
        files: [
          { model_type: 'loras', filename: 'a', size_bytes: 1, status: 'new', file_hash: 'h1' },
          { model_type: 'loras', filename: 'b', size_bytes: 2, status: 'new', file_hash: 'h2' },
        ],
      }),
    );
    component.sourceRoot.set('/src/models');
    component.toggleFile('loras', 'a', true);
    component.startImport();
    await Promise.resolve();
    expect(importService.startImport).toHaveBeenCalledWith('/src/models', [
      { model_type: 'loras', filename: 'a', file_hash: 'h1' },
    ]);
  });

  it('does not start an import with nothing selected', () => {
    component.startImport();
    expect(importService.startImport).not.toHaveBeenCalled();
    expect(component.errorKey()).toBe('import.errors.no_files_selected');
  });

  it('does not collide when a filename or model type contains a space', () => {
    component.applyScanState(
      jobState({
        files: [
          {
            model_type: 'loras alpha',
            filename: 'beta',
            size_bytes: 1,
            status: 'new',
            file_hash: 'h1',
          },
          {
            model_type: 'loras',
            filename: 'alpha beta',
            size_bytes: 2,
            status: 'new',
            file_hash: 'h2',
          },
        ],
      }),
    );
    component.toggleFile('loras alpha', 'beta', true);
    expect(component.isSelected('loras alpha', 'beta')).toBe(true);
    expect(component.isSelected('loras', 'alpha beta')).toBe(false);
    expect(component.selectedCount()).toBe(1);
  });
});

describe('models/import routing', () => {
  it('is declared before the catalog-detail wildcard', async () => {
    const { routes } = await import('../../app.routes');
    const importIndex = routes.findIndex((r) => r.path === 'models/import');
    const platformIndex = routes.findIndex((r) => r.path === 'models/:platform');
    expect(importIndex).toBeGreaterThanOrEqual(0);
    expect(importIndex).toBeLessThan(platformIndex);
  });
});
