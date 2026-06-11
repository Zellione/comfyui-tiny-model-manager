import { signal, WritableSignal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { of, EMPTY } from 'rxjs';
import { vi } from 'vitest';
import { InstalledFilesService } from './installed-files';
import { DownloadService, DownloadTask } from './download';
import { ModelService } from './model';
import { NotificationService } from './notification';
import { KeywordsService } from './keywords';
import { CivitaiFile } from './civitai';
import { FilenameKeyword } from '../utils/filename-detector';

const mockDownloadService = {
  activeTasks$: of([] as DownloadTask[]),
  completedTasks$: EMPTY,
  startDownload: vi.fn().mockReturnValue(of({})),
};

const mockModelService = {
  listModels: vi.fn().mockReturnValue(of({})),
};

const mockNotifService = { show: vi.fn() };

const mockKeywordsService = {
  getKeywords: vi.fn(() => of([] as FilenameKeyword[])),
};

const mockCivitaiFile: CivitaiFile = {
  id: 101,
  name: 'model.safetensors',
  type: 'Model',
  sizeKB: 1024,
  downloadUrl: 'https://example.com/model.safetensors',
  primary: true,
  metadata: { format: 'SafeTensor', size: 'full', fp: 'fp16' },
};

function makeTask(overrides: Partial<DownloadTask>): DownloadTask {
  return {
    id: 'task-1',
    url: 'https://example.com/m.safetensors',
    model_type: 'checkpoints',
    filename: 'm.safetensors',
    platform: 'civitai',
    source_id: '1',
    status: 'downloading',
    progress: 0,
    downloaded_bytes: 0,
    total_bytes: 0,
    error: null,
    history_id: null,
    ...overrides,
  };
}

function createService(): InstalledFilesService {
  TestBed.configureTestingModule({
    providers: [
      InstalledFilesService,
      { provide: DownloadService, useValue: mockDownloadService },
      { provide: ModelService, useValue: mockModelService },
      { provide: NotificationService, useValue: mockNotifService },
      { provide: KeywordsService, useValue: mockKeywordsService },
    ],
  });
  return TestBed.inject(InstalledFilesService);
}

describe('InstalledFilesService — fileStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDownloadService.activeTasks$ = of([]);
    mockModelService.listModels.mockReturnValue(of({}));
    mockKeywordsService.getKeywords.mockReturnValue(of([]));
  });

  it('returns idle for an unknown filename', () => {
    const svc = createService();
    expect(svc.fileStatus('unknown.safetensors')).toBe('idle');
  });

  it('returns installed when basename is in installedFilenames', () => {
    const svc = createService();
    svc.installedFilenames.set(new Set(['model.safetensors']));
    expect(svc.fileStatus('model.safetensors')).toBe('installed');
  });

  it('strips subfolder prefix before matching', () => {
    const svc = createService();
    svc.installedFilenames.set(new Set(['model.safetensors']));
    expect(svc.fileStatus('split_files/model.safetensors')).toBe('installed');
  });

  it('returns downloading for a task with downloading status', () => {
    mockDownloadService.activeTasks$ = of([makeTask({ status: 'downloading' })]);
    const svc = createService();
    expect(svc.fileStatus('m.safetensors')).toBe('downloading');
  });

  it('returns error for a task with error status', () => {
    mockDownloadService.activeTasks$ = of([makeTask({ status: 'error', error: 'boom' })]);
    const svc = createService();
    expect(svc.fileStatus('m.safetensors')).toBe('error');
  });

  it('returns installed for a task with done status', () => {
    mockDownloadService.activeTasks$ = of([makeTask({ status: 'done', progress: 100 })]);
    const svc = createService();
    expect(svc.fileStatus('m.safetensors')).toBe('installed');
  });

  it('seeds installedFilenames from listModels on construction', () => {
    mockModelService.listModels.mockReturnValue(
      of({ checkpoints: [{ filename: 'seed.safetensors' }] }),
    );
    const svc = createService();
    expect(svc.fileStatus('seed.safetensors')).toBe('installed');
  });
});

describe('InstalledFilesService — override helpers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDownloadService.activeTasks$ = of([]);
    mockModelService.listModels.mockReturnValue(of({}));
    mockKeywordsService.getKeywords.mockReturnValue(of([]));
  });

  it('readOverride returns the fallback for an unknown key', () => {
    const svc = createService();
    const map = signalRecord<string>();
    expect(svc.readOverride(map, 'missing', 'fallback')).toBe('fallback');
  });

  it('writeOverride stores a value retrievable by readOverride', () => {
    const svc = createService();
    const map = signalRecord<string>();
    svc.writeOverride(map, 'k', 'v');
    expect(svc.readOverride(map, 'k', 'fallback')).toBe('v');
  });

  it('fileKey combines versionId and file id', () => {
    const svc = createService();
    expect(svc.fileKey(7, mockCivitaiFile)).toBe('7_101');
  });
});

describe('InstalledFilesService — enqueue', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDownloadService.activeTasks$ = of([]);
    mockModelService.listModels.mockReturnValue(of({}));
    mockKeywordsService.getKeywords.mockReturnValue(of([]));
    mockDownloadService.startDownload.mockReturnValue(of({}));
  });

  it('starts the download and toasts on success', () => {
    const svc = createService();
    svc.enqueue(
      'https://example.com/a.safetensors',
      'loras',
      'a.safetensors',
      'civitai',
      '5',
      'Pony',
    );
    expect(mockDownloadService.startDownload).toHaveBeenCalledWith(
      'https://example.com/a.safetensors',
      'loras',
      'a.safetensors',
      'civitai',
      '5',
      'Pony',
    );
    expect(mockNotifService.show).toHaveBeenCalledWith(
      'success',
      expect.stringContaining('a.safetensors'),
    );
  });
});

function signalRecord<T>(): WritableSignal<Record<string, T>> {
  return signal<Record<string, T>>({});
}
