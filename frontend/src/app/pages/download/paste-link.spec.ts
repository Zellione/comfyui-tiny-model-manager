import { TestBed } from '@angular/core/testing';
import { of, EMPTY } from 'rxjs';
import { vi } from 'vitest';
import { PasteLink } from './paste-link';
import { CivitaiService, CivitaiFile, CivitaiVersion } from '../../services/civitai';
import { HuggingFaceService } from '../../services/huggingface';
import { DownloadService, DownloadTask } from '../../services/download';
import { ModelService } from '../../services/model';
import { NotificationService } from '../../services/notification';
import { KeywordsService } from '../../services/keywords';
import { FilenameKeyword } from '../../utils/filename-detector';

const mockCivitaiService = {
  getVersions: vi.fn().mockReturnValue(EMPTY),
  resolveDirectLink: vi.fn().mockReturnValue(EMPTY),
};

const mockHfService = {
  getFiles: vi.fn().mockReturnValue(EMPTY),
  resolveDirectLink: vi.fn().mockReturnValue(EMPTY),
};

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
  downloadUrl: 'https://civitai.com/model.safetensors',
  primary: true,
  metadata: { format: 'SafeTensor', size: 'full', fp: 'fp16' },
};

const sdxlKeyword = {
  id: 1,
  keyword: 'sdxl',
  base_model: 'SDXL 1.0',
  model_type: null,
  sort_order: 10,
};
const loraKeyword = {
  id: 2,
  keyword: 'lora',
  base_model: null,
  model_type: 'loras',
  sort_order: 20,
};

async function configureTestBed() {
  await TestBed.configureTestingModule({
    imports: [PasteLink],
    providers: [
      { provide: CivitaiService, useValue: mockCivitaiService },
      { provide: HuggingFaceService, useValue: mockHfService },
      { provide: DownloadService, useValue: mockDownloadService },
      { provide: ModelService, useValue: mockModelService },
      { provide: NotificationService, useValue: mockNotifService },
      { provide: KeywordsService, useValue: mockKeywordsService },
    ],
  }).compileComponents();
}

async function createFixture() {
  const fixture = TestBed.createComponent(PasteLink);
  fixture.detectChanges();
  await fixture.whenStable();
  return fixture;
}

describe('PasteLink — per-file override accessors', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockKeywordsService.getKeywords.mockReturnValue(of([]));
    mockModelService.listModels.mockReturnValue(of({}));
    mockDownloadService.activeTasks$ = of([]);
    await configureTestBed();
  });

  it('linkHfRowBaseModel returns empty string for unknown key', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.linkHfRowBaseModel('unknown.safetensors')).toBe('');
  });

  it('setLinkHfRowBaseModel stores a value retrievable by linkHfRowBaseModel', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.setLinkHfRowBaseModel('model.safetensors', 'Flux.1 D');
    expect(c.linkHfRowBaseModel('model.safetensors')).toBe('Flux.1 D');
  });

  it('linkCivitaiFileBaseModel returns empty string for unknown key', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.linkCivitaiFileBaseModel(1, mockCivitaiFile)).toBe('');
  });

  it('setLinkCivitaiFileBaseModel stores a value retrievable by linkCivitaiFileBaseModel', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.setLinkCivitaiFileBaseModel(1, mockCivitaiFile, 'SD 1.5');
    expect(c.linkCivitaiFileBaseModel(1, mockCivitaiFile)).toBe('SD 1.5');
  });

  it('linkHfRowType defaults to checkpoints, settable per file', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    expect(c.linkHfRowType('a.safetensors')).toBe('checkpoints');
    c.setLinkHfRowType('a.safetensors', 'loras');
    expect(c.linkHfRowType('a.safetensors')).toBe('loras');
  });
});

describe('PasteLink — applyLinkResolution', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockKeywordsService.getKeywords.mockReturnValue(of([sdxlKeyword, loraKeyword]));
    mockModelService.listModels.mockReturnValue(of({}));
    mockDownloadService.activeTasks$ = of([]);
    await configureTestBed();
  });

  it('hf-resolve: sets linkBaseModel and linkImages from resolved data', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.linkResolving.set(true);
    (c as any).applyLinkResolution({
      tag: 'hf-resolve',
      filename: 'sdxl_lora.safetensors',
      image_urls: ['https://image.civitai.com/img.jpg'],
    });
    expect(c.linkBaseModel()).toBe('SDXL 1.0');
    expect(c.linkImages()).toEqual(['https://image.civitai.com/img.jpg']);
    expect(c.linkResolving()).toBe(false);
  });

  it('hf-resolve: sets linkModelType when keyword provides model_type', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    (c as any).applyLinkResolution({ tag: 'hf-resolve', filename: 'sdxl_lora.safetensors' });
    expect(c.linkModelType()).toBe('loras');
  });

  it('hf-resolve: does not change linkModelType when no model_type keyword matches', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.linkModelType.set('vae');
    (c as any).applyLinkResolution({ tag: 'hf-resolve', filename: 'sdxl_checkpoint.safetensors' });
    expect(c.linkModelType()).toBe('vae');
    expect(c.linkBaseModel()).toBe('SDXL 1.0');
  });

  it('civitai-download: sets linkResolved, linkModelType, linkImages, and linkBaseModel', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.linkResolving.set(true);
    const result = {
      tag: 'civitai-download' as const,
      filename: 'sdxl_model.safetensors',
      model_type: 'checkpoints',
      size_kb: 1024,
      image_urls: ['https://image.civitai.com/img1.jpg'],
    };
    (c as any).applyLinkResolution(result);
    expect(c.linkBaseModel()).toBe('SDXL 1.0');
    expect(c.linkModelType()).toBe('checkpoints');
    expect(c.linkImages()).toEqual(['https://image.civitai.com/img1.jpg']);
    expect(c.linkResolved()).toBe(result);
    expect(c.linkResolving()).toBe(false);
  });

  it('hf-repo: populates linkHfFiles and sets base models for matching filenames', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.linkResolving.set(true);
    const files = [
      {
        filename: 'sdxl_model.safetensors',
        size: 1024,
        url: 'https://huggingface.co/a.safetensors',
      },
      {
        filename: 'plain_model.safetensors',
        size: 512,
        url: 'https://huggingface.co/b.safetensors',
      },
    ];
    (c as any).applyLinkResolution({ tag: 'hf-repo', files });
    expect(c.linkHfFiles()).toEqual(files);
    expect(c.linkHfRowBaseModels()['sdxl_model.safetensors']).toBe('SDXL 1.0');
    expect(c.linkHfRowBaseModels()['plain_model.safetensors']).toBeUndefined();
    expect(c.linkResolving()).toBe(false);
  });

  it('hf-repo: sets linkHfRowTypes for matching model_type keywords', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    (c as any).applyLinkResolution({
      tag: 'hf-repo',
      files: [
        { filename: 'my_lora.safetensors', size: 512, url: 'https://huggingface.co/c.safetensors' },
      ],
    });
    expect(c.linkHfRowTypes()['my_lora.safetensors']).toBe('loras');
  });

  it('civitai-model: sets linkVersions and detects base model from filename when version lacks one', async () => {
    const versions: CivitaiVersion[] = [
      {
        id: 10,
        name: 'v1',
        baseModel: '',
        downloadUrl: 'https://civitai.com',
        trainedWords: [],
        images: [],
        files: [
          {
            id: 200,
            name: 'sdxl_checkpoint.safetensors',
            type: 'Model',
            sizeKB: 2048,
            downloadUrl: 'https://civitai.com/d.safetensors',
            primary: true,
            metadata: { format: 'SafeTensor', size: 'full', fp: 'fp16' },
          },
        ],
      },
    ];
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.linkResolving.set(true);
    (c as any).applyLinkResolution({ tag: 'civitai-model', versions, model_type: 'checkpoints' });
    expect(c.linkVersions()).toEqual(versions);
    expect(c.linkModelType()).toBe('checkpoints');
    expect(c.linkCivitaiFileBaseModels()['10_200']).toBe('SDXL 1.0');
    expect(c.linkResolving()).toBe(false);
  });

  it('civitai-model: uses version.baseModel when set, ignoring filename detection', async () => {
    const versions: CivitaiVersion[] = [
      {
        id: 11,
        name: 'v2',
        baseModel: 'Pony',
        downloadUrl: 'https://civitai.com',
        trainedWords: [],
        images: [],
        files: [
          {
            id: 201,
            name: 'sdxl_checkpoint.safetensors',
            type: 'Model',
            sizeKB: 2048,
            downloadUrl: 'https://civitai.com/e.safetensors',
            primary: true,
            metadata: { format: 'SafeTensor', size: 'full', fp: 'fp16' },
          },
        ],
      },
    ];
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    (c as any).applyLinkResolution({ tag: 'civitai-model', versions });
    expect(c.linkCivitaiFileBaseModels()['11_201']).toBe('Pony');
  });

  it('null result: sets linkResolving to false without touching other state', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.linkResolving.set(true);
    c.linkBaseModel.set('existing');
    (c as any).applyLinkResolution(null);
    expect(c.linkResolving()).toBe(false);
    expect(c.linkBaseModel()).toBe('existing');
  });
});

describe('PasteLink — downloads and selection', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockKeywordsService.getKeywords.mockReturnValue(of([]));
    mockModelService.listModels.mockReturnValue(of({}));
    mockDownloadService.activeTasks$ = of([]);
    mockDownloadService.startDownload.mockReturnValue(of({}));
    await configureTestBed();
  });

  it('downloadLinkFile enqueues with the file download url and per-file type', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.setLinkCivitaiFileType(5, mockCivitaiFile, 'loras');
    c.downloadLinkFile(mockCivitaiFile, 5);
    expect(mockDownloadService.startDownload).toHaveBeenCalledWith(
      mockCivitaiFile.downloadUrl,
      'loras',
      mockCivitaiFile.name,
      'civitai',
      '5',
      '',
    );
    expect(mockNotifService.show).toHaveBeenCalledWith(
      'success',
      expect.stringContaining(mockCivitaiFile.name),
    );
  });

  it('toggleLinkCivitaiFile selects then deselects a file', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    expect(c.isLinkCivitaiFileSelected(5, mockCivitaiFile)).toBe(false);
    c.toggleLinkCivitaiFile(5, mockCivitaiFile);
    expect(c.isLinkCivitaiFileSelected(5, mockCivitaiFile)).toBe(true);
    expect(c.linkCivitaiSelectedCount()).toBe(1);
    c.toggleLinkCivitaiFile(5, mockCivitaiFile);
    expect(c.isLinkCivitaiFileSelected(5, mockCivitaiFile)).toBe(false);
  });

  it('downloadSelectedLinkCivitai enqueues all selected then clears the selection', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.toggleLinkCivitaiFile(5, mockCivitaiFile);
    c.downloadSelectedLinkCivitai();
    expect(mockDownloadService.startDownload).toHaveBeenCalledTimes(1);
    expect(c.linkCivitaiSelectedCount()).toBe(0);
  });
});

describe('PasteLink — fileStatus', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockKeywordsService.getKeywords.mockReturnValue(of([]));
    mockDownloadService.activeTasks$ = of([]);
    await configureTestBed();
  });

  it('returns installed for a known installed basename (subfolder-stripped)', async () => {
    mockModelService.listModels.mockReturnValue(
      of({ checkpoints: [{ filename: 'model.safetensors' }] }),
    );
    await configureTestBed();
    const fixture = await createFixture();
    expect(fixture.componentInstance.fileStatus('split_files/model.safetensors')).toBe('installed');
  });

  it('returns idle for an unknown file', async () => {
    mockModelService.listModels.mockReturnValue(of({}));
    const fixture = await createFixture();
    expect(fixture.componentInstance.fileStatus('nope.safetensors')).toBe('idle');
  });
});
