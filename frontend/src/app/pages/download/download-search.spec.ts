import { TestBed } from '@angular/core/testing';
import { of, throwError, EMPTY } from 'rxjs';
import { vi } from 'vitest';
import { HttpErrorResponse } from '@angular/common/http';
import { DownloadSearch } from './download-search';
import { CivitaiService, CivitaiFile, CivitaiModel, CivitaiVersion } from '../../services/civitai';
import { HuggingFaceService, HfModel } from '../../services/huggingface';
import { DownloadService, DownloadTask } from '../../services/download';
import { ModelService } from '../../services/model';
import { NotificationService } from '../../services/notification';
import { KeywordsService } from '../../services/keywords';
import { InstalledFilesService } from '../../services/installed-files';
import { FilenameKeyword } from '../../utils/filename-detector';

const civitaiModel = (id: number) => ({
  id,
  name: `Model ${id}`,
  type: 'LORA',
  description: '',
  tags: [],
  modelVersions: [],
  creator: { username: '' },
  stats: { downloadCount: 0, thumbsUpCount: 0, thumbsDownCount: 0 },
});

const mockCivitaiService = {
  search: vi.fn(),
  getVersions: vi.fn().mockReturnValue(EMPTY),
};

const mockHfService = {
  search: vi.fn(),
  getFiles: vi.fn().mockReturnValue(EMPTY),
  getReadme: vi.fn().mockReturnValue(EMPTY),
};

const mockDownloadService = {
  activeTasks$: of([] as DownloadTask[]),
  completedTasks$: EMPTY,
  startDownload: vi.fn().mockReturnValue(of({})),
};

const mockModelService = {
  listModels: vi.fn().mockReturnValue(of({})),
};

const mockNotifService = {
  show: vi.fn(),
};

const mockKeywordsService = {
  getKeywords: vi.fn(() => of([] as FilenameKeyword[])),
};

async function configureTestBed() {
  await TestBed.configureTestingModule({
    imports: [DownloadSearch],
    providers: [
      InstalledFilesService,
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
  const fixture = TestBed.createComponent(DownloadSearch);
  fixture.detectChanges();
  await fixture.whenStable();
  return fixture;
}

describe('DownloadSearch — F-37 Load More', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockModelService.listModels.mockReturnValue(of({}));
    mockCivitaiService.search.mockReturnValue(
      of({ items: [civitaiModel(1)], metadata: { nextCursor: 'cur1' } }),
    );
    mockHfService.search.mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 }));
    await configureTestBed();
  });

  describe('initial signal state', () => {
    it('loadMoreError starts empty', async () => {
      const fixture = await createFixture();
      expect(fixture.componentInstance.loadMoreError()).toBe('');
    });

    it('activeHasMore reflects civitaiHasMore when platform is civitai', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      c.civitaiHasMore.set(true);
      c.hfHasMore.set(false);
      expect(c.activeHasMore()).toBe(true);
    });

    it('activeHasMore reflects hfHasMore when platform is huggingface', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('huggingface');
      c.civitaiHasMore.set(false);
      c.hfHasMore.set(true);
      expect(c.activeHasMore()).toBe(true);
    });
  });

  describe('search() resets error', () => {
    it('clears loadMoreError when a new search is triggered', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.loadMoreError.set('previous error');

      c.search();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBe('');
    });

    it('clears searchError when a new search is triggered', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.searchError.set('previous search error');

      c.search();
      await fixture.whenStable();

      expect(c.searchError()).toBe('');
    });
  });

  describe('search() error handling', () => {
    it('sets searchError on CivitAI HTTP error', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      const err = new HttpErrorResponse({ error: { error: 'Rate limited' }, status: 429 });
      mockCivitaiService.search.mockReturnValue(throwError(() => err));

      c.search();
      await fixture.whenStable();

      expect(c.searchError()).toBe('Rate limited');
      expect(c.searching()).toBe(false);
    });

    it('sets searchError on HuggingFace HTTP error', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('huggingface');
      const err = new HttpErrorResponse({ error: { error: 'Service unavailable' }, status: 503 });
      mockHfService.search.mockReturnValue(throwError(() => err));

      c.search();
      await fixture.whenStable();

      expect(c.searchError()).toBe('Service unavailable');
      expect(c.searching()).toBe(false);
    });

    it('falls back to err.message when error body has no error field', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      const err = new HttpErrorResponse({ error: null, status: 0, statusText: 'Unknown Error' });
      mockCivitaiService.search.mockReturnValue(throwError(() => err));

      c.search();
      await fixture.whenStable();

      expect(c.searchError()).toBeTruthy();
      expect(c.searching()).toBe(false);
    });
  });

  describe('loadMore() — CivitAI', () => {
    it('appends items and updates pagination on success', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      c.civitaiResults.set([civitaiModel(1)]);
      mockCivitaiService.search.mockReturnValue(
        of({ items: [civitaiModel(2)], metadata: { nextCursor: 'cur2' } }),
      );

      c.loadMore();
      await fixture.whenStable();

      expect(c.civitaiResults()).toHaveLength(2);
      expect(c.civitaiCursor()).toBe('cur2');
      expect(c.civitaiHasMore()).toBe(true);
      expect(c.loadMoreError()).toBe('');
    });

    it('sets loadMoreError and shows error toast on HTTP error', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      const err = new HttpErrorResponse({ error: { error: 'Rate limited' }, status: 429 });
      mockCivitaiService.search.mockReturnValue(throwError(() => err));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBe('Rate limited');
      expect(mockNotifService.show).toHaveBeenCalledWith('error', 'Rate limited');
    });

    it('falls back to err.message when error body has no error field', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      const err = new HttpErrorResponse({ error: null, status: 500, statusText: 'Server Error' });
      mockCivitaiService.search.mockReturnValue(throwError(() => err));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBeTruthy();
      expect(mockNotifService.show).toHaveBeenCalledWith('error', expect.any(String));
    });

    it('sets loadMoreError to "No results returned" when items are empty (first attempt)', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      mockCivitaiService.search.mockReturnValue(of({ items: [], metadata: { nextCursor: '' } }));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBe('No results returned');
      expect(mockNotifService.show).toHaveBeenCalledWith('error', 'No results returned');
    });

    it('treats empty items as end of results on retry (wasError=true)', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      c.loadMoreError.set('previous error');
      c.civitaiResults.set([civitaiModel(1)]);
      mockCivitaiService.search.mockReturnValue(of({ items: [], metadata: { nextCursor: '' } }));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBe('');
      expect(c.civitaiHasMore()).toBe(false);
      expect(mockNotifService.show).not.toHaveBeenCalled();
      expect(c.civitaiResults()).toHaveLength(1);
    });

    it('sets loadingMore to false after error', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      mockCivitaiService.search.mockReturnValue(throwError(() => new Error('fail')));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadingMore()).toBe(false);
    });

    it('clears previous loadMoreError when retrying', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('civitai');
      c.loadMoreError.set('old error');
      mockCivitaiService.search.mockReturnValue(
        of({ items: [civitaiModel(3)], metadata: { nextCursor: '' } }),
      );

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBe('');
    });
  });

  describe('loadMore() — HuggingFace', () => {
    it('appends items and updates pagination on success', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('huggingface');
      const existingModel = { id: 'a/m1', modelId: 'a/m1', downloads: 0, tags: [] };
      c.hfResults.set([existingModel]);
      const newModel = { id: 'a/m2', modelId: 'a/m2', downloads: 0, tags: [] };
      mockHfService.search.mockReturnValue(of({ items: [newModel], hasMore: false, nextPage: 2 }));

      c.loadMore();
      await fixture.whenStable();

      expect(c.hfResults()).toHaveLength(2);
      expect(c.hfPage()).toBe(2);
      expect(c.hfHasMore()).toBe(false);
      expect(c.loadMoreError()).toBe('');
    });

    it('sets loadMoreError and shows error toast on HTTP error', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('huggingface');
      const err = new HttpErrorResponse({ error: { error: 'Model not found' }, status: 404 });
      mockHfService.search.mockReturnValue(throwError(() => err));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBe('Model not found');
      expect(mockNotifService.show).toHaveBeenCalledWith('error', 'Model not found');
    });

    it('sets loadMoreError to "No results returned" when items are empty (first attempt)', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('huggingface');
      mockHfService.search.mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 }));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBe('No results returned');
      expect(mockNotifService.show).toHaveBeenCalledWith('error', 'No results returned');
    });

    it('treats empty items as end of results on retry (wasError=true)', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('huggingface');
      c.loadMoreError.set('previous error');
      mockHfService.search.mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 }));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadMoreError()).toBe('');
      expect(c.hfHasMore()).toBe(false);
      expect(mockNotifService.show).not.toHaveBeenCalled();
    });

    it('sets loadingMore to false after error', async () => {
      const fixture = await createFixture();
      const c = fixture.componentInstance;
      c.platform.set('huggingface');
      mockHfService.search.mockReturnValue(throwError(() => new Error('fail')));

      c.loadMore();
      await fixture.whenStable();

      expect(c.loadingMore()).toBe(false);
    });
  });
});

describe('DownloadSearch — tag methods', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockDownloadService.activeTasks$ = of([] as DownloadTask[]);
    mockModelService.listModels.mockReturnValue(of({}));
    mockCivitaiService.search.mockReturnValue(of({ items: [], metadata: {} }));
    mockHfService.search.mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 }));
    await configureTestBed();
  });

  it('addTag appends a trimmed tag to tagFilter and clears tagInput', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.tagInput.set('anime');
    c.addTag('  anime  ');
    expect(c.tagFilter()).toContain('anime');
    expect(c.tagInput()).toBe('');
  });

  it('addTag ignores duplicate tags', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.addTag('lora');
    c.addTag('lora');
    expect(c.tagFilter()).toHaveLength(1);
  });

  it('addTag ignores blank strings', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.addTag('   ');
    expect(c.tagFilter()).toHaveLength(0);
  });

  it('addTagFromInput adds the current tagInput value', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.tagInput.set('  lora  ');
    c.addTagFromInput();
    expect(c.tagFilter()).toContain('lora');
    expect(c.tagInput()).toBe('');
  });

  it('addTagFromInput does nothing when tagInput is blank', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.tagInput.set('');
    c.addTagFromInput();
    expect(c.tagFilter()).toHaveLength(0);
  });

  it('removeTag removes the specified tag and keeps others', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.tagFilter.set(['anime', 'lora']);
    c.removeTag('anime');
    expect(c.tagFilter()).not.toContain('anime');
    expect(c.tagFilter()).toContain('lora');
  });
});

describe('DownloadSearch — F-80 HuggingFace model selection', () => {
  const hfModel = (): HfModel => ({
    id: 'user/repo',
    modelId: 'user/repo',
    downloads: 0,
    tags: [],
    description: 'desc',
  });

  beforeEach(async () => {
    vi.clearAllMocks();
    mockModelService.listModels.mockReturnValue(of({}));
    mockCivitaiService.search.mockReturnValue(of({ items: [], metadata: {} }));
    mockHfService.search.mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 }));
    mockHfService.getFiles.mockReturnValue(EMPTY);
    await configureTestBed();
  });

  it('selectHf resets galleryIndex to 0', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.galleryIndex.set(3);
    c.selectHf(hfModel());
    expect(c.galleryIndex()).toBe(0);
  });
});

const mockCivitaiFile: CivitaiFile = {
  id: 101,
  name: 'model.safetensors',
  type: 'Model',
  sizeKB: 1024,
  downloadUrl: 'https://example.com/model.safetensors',
  primary: true,
  metadata: { format: 'SafeTensor', size: 'full', fp: 'fp16' },
};

describe('DownloadSearch — F-82 base model signals', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockKeywordsService.getKeywords.mockReturnValue(of([]));
    mockModelService.listModels.mockReturnValue(of({}));
    mockCivitaiService.search.mockReturnValue(of({ items: [], metadata: {} }));
    mockHfService.search.mockReturnValue(of({ items: [], hasMore: false, nextPage: 1 }));
    mockDownloadService.activeTasks$ = of([]);
    await configureTestBed();
  });

  it('hfRowBaseModel returns empty string for unknown key', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.hfRowBaseModel('unknown.safetensors')).toBe('');
  });

  it('setHfRowBaseModel stores a value retrievable by hfRowBaseModel', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.setHfRowBaseModel('model.safetensors', 'SDXL 1.0');
    expect(c.hfRowBaseModel('model.safetensors')).toBe('SDXL 1.0');
  });

  it('civitaiFileBaseModel returns empty string for unknown key', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.civitaiFileBaseModel(1, mockCivitaiFile)).toBe('');
  });

  it('setCivitaiFileBaseModel stores a value retrievable by civitaiFileBaseModel', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.setCivitaiFileBaseModel(1, mockCivitaiFile, 'Pony');
    expect(c.civitaiFileBaseModel(1, mockCivitaiFile)).toBe('Pony');
  });
});

const richCivitaiModel = (): CivitaiModel => ({
  id: 7,
  name: 'Rich Model',
  type: 'Checkpoint',
  description: 'desc',
  tags: ['anime', 'style'],
  modelVersions: [
    {
      id: 70,
      name: 'v1',
      baseModel: 'SDXL 1.0',
      downloadUrl: 'https://civitai.com/v1',
      trainedWords: ['trigger1', 'trigger2'],
      images: [{ url: 'https://img/a.jpg' }, { url: 'https://img/b.mp4' }, { url: '' }],
      files: [mockCivitaiFile],
    },
  ],
  creator: { username: 'alice' },
  stats: { downloadCount: 42, thumbsUpCount: 0, thumbsDownCount: 0 },
});

const hfGalleryModel = (): HfModel => ({
  id: 'user/repo',
  modelId: 'user/repo',
  downloads: 5,
  tags: ['tag'],
  images: ['https://hf/img1.jpg', 'https://hf/img2.jpg'],
});

describe('DownloadSearch — display helpers', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockKeywordsService.getKeywords.mockReturnValue(of([]));
    mockModelService.listModels.mockReturnValue(of({}));
    mockDownloadService.activeTasks$ = of([]);
    await configureTestBed();
  });

  it('civitaiThumb returns the first version image url', async () => {
    const c = (await createFixture()).componentInstance;
    expect(c.civitaiThumb(richCivitaiModel())).toBe('https://img/a.jpg');
  });

  it('civitaiThumb returns empty string when there are no images', async () => {
    const c = (await createFixture()).componentInstance;
    const model = { ...richCivitaiModel(), modelVersions: [] };
    expect(c.civitaiThumb(model)).toBe('');
  });

  it('civitaiGalleryImages drops blank urls and caps at 8', async () => {
    const c = (await createFixture()).componentInstance;
    expect(c.civitaiGalleryImages(richCivitaiModel())).toEqual([
      'https://img/a.jpg',
      'https://img/b.mp4',
    ]);
  });

  it('currentGalleryUrl follows galleryIndex', async () => {
    const c = (await createFixture()).componentInstance;
    const model = richCivitaiModel();
    expect(c.currentGalleryUrl(model)).toBe('https://img/a.jpg');
    c.setGalleryIndex(1);
    expect(c.currentGalleryUrl(model)).toBe('https://img/b.mp4');
  });

  it('civitaiModelBaseModel returns the first version base model', async () => {
    const c = (await createFixture()).componentInstance;
    expect(c.civitaiModelBaseModel(richCivitaiModel())).toBe('SDXL 1.0');
  });

  it('civitaiTriggerWords returns the first version trained words', async () => {
    const c = (await createFixture()).componentInstance;
    expect(c.civitaiTriggerWords(richCivitaiModel())).toEqual(['trigger1', 'trigger2']);
  });

  it('civitaiSourceUrl builds a model url from the id', async () => {
    const c = (await createFixture()).componentInstance;
    expect(c.civitaiSourceUrl(richCivitaiModel())).toBe('https://civitai.com/models/7');
  });

  it('hfGalleryImages and currentHfGalleryUrl follow galleryIndex', async () => {
    const c = (await createFixture()).componentInstance;
    const model = hfGalleryModel();
    expect(c.hfGalleryImages(model)).toHaveLength(2);
    expect(c.currentHfGalleryUrl(model)).toBe('https://hf/img1.jpg');
    c.setGalleryIndex(1);
    expect(c.currentHfGalleryUrl(model)).toBe('https://hf/img2.jpg');
  });

  it('hfSourceUrl builds a repo url from the modelId', async () => {
    const c = (await createFixture()).componentInstance;
    expect(c.hfSourceUrl(hfGalleryModel())).toBe('https://huggingface.co/user/repo');
  });

  it('onImgError hides the broken image element', async () => {
    const c = (await createFixture()).componentInstance;
    const img = document.createElement('img');
    c.onImgError({ target: img } as unknown as Event);
    expect(img.style.display).toBe('none');
  });

  it('fileStatus delegates to the installed-files service', async () => {
    const c = (await createFixture()).componentInstance;
    expect(c.fileStatus('nope.safetensors')).toBe('idle');
  });
});

describe('DownloadSearch — CivitAI selection and downloads', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockKeywordsService.getKeywords.mockReturnValue(of([]));
    mockModelService.listModels.mockReturnValue(of({}));
    mockDownloadService.activeTasks$ = of([]);
    mockDownloadService.startDownload.mockReturnValue(of({}));
    await configureTestBed();
  });

  it('selectCivitai loads versions and seeds per-file type/base-model overrides', async () => {
    const versions: CivitaiVersion[] = richCivitaiModel().modelVersions;
    mockCivitaiService.getVersions.mockReturnValue(of({ versions, model_type: 'checkpoints' }));
    const fixture = await createFixture();
    const c = fixture.componentInstance;

    c.selectCivitai(richCivitaiModel());
    await fixture.whenStable();

    expect(c.versions()).toEqual(versions);
    expect(c.civitaiFileType(70, mockCivitaiFile)).toBe('checkpoints');
    expect(c.civitaiFileBaseModel(70, mockCivitaiFile)).toBe('SDXL 1.0');
    expect(c.loadingVersions()).toBe(false);
  });

  it('selectCivitai sets versionsError on failure', async () => {
    mockCivitaiService.getVersions.mockReturnValue(
      throwError(() => ({ error: { error: 'boom' } })),
    );
    const fixture = await createFixture();
    const c = fixture.componentInstance;

    c.selectCivitai(richCivitaiModel());
    await fixture.whenStable();

    expect(c.versionsError()).toBe('boom');
    expect(c.loadingVersions()).toBe(false);
  });

  it('toggleCivitaiFile selects then deselects a file', async () => {
    const c = (await createFixture()).componentInstance;
    expect(c.isCivitaiFileSelected(5, mockCivitaiFile)).toBe(false);
    c.toggleCivitaiFile(5, mockCivitaiFile);
    expect(c.isCivitaiFileSelected(5, mockCivitaiFile)).toBe(true);
    expect(c.selectedCivitaiCount()).toBe(1);
    c.toggleCivitaiFile(5, mockCivitaiFile);
    expect(c.isCivitaiFileSelected(5, mockCivitaiFile)).toBe(false);
  });

  it('downloadFile enqueues with the file url and per-file overrides', async () => {
    const c = (await createFixture()).componentInstance;
    c.setCivitaiFileType(5, mockCivitaiFile, 'loras');
    c.setCivitaiFileBaseModel(5, mockCivitaiFile, 'Pony');
    c.downloadFile(mockCivitaiFile, 5);
    expect(mockDownloadService.startDownload).toHaveBeenCalledWith(
      mockCivitaiFile.downloadUrl,
      'loras',
      mockCivitaiFile.name,
      'civitai',
      '5',
      'Pony',
    );
  });

  it('downloadSelectedCivitai enqueues all selected then clears the selection', async () => {
    const c = (await createFixture()).componentInstance;
    c.toggleCivitaiFile(5, mockCivitaiFile);
    c.downloadSelectedCivitai();
    expect(mockDownloadService.startDownload).toHaveBeenCalledTimes(1);
    expect(c.selectedCivitaiCount()).toBe(0);
  });
});

describe('DownloadSearch — HuggingFace selection and downloads', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockKeywordsService.getKeywords.mockReturnValue(of([]));
    mockModelService.listModels.mockReturnValue(of({}));
    mockDownloadService.activeTasks$ = of([]);
    mockDownloadService.startDownload.mockReturnValue(of({}));
    await configureTestBed();
  });

  it('selectHf loads files and uses the inline description without fetching the readme', async () => {
    const files = [{ filename: 'split_files/model.safetensors', size: 10, url: 'https://hf/m' }];
    mockHfService.getFiles.mockReturnValue(of(files));
    const fixture = await createFixture();
    const c = fixture.componentInstance;

    c.selectHf({
      id: 'user/repo',
      modelId: 'user/repo',
      downloads: 0,
      tags: [],
      description: 'inline',
    });
    await fixture.whenStable();

    expect(c.hfFiles()).toEqual(files);
    expect(c.hfDescription()).toBe('inline');
    expect(mockHfService.getReadme).not.toHaveBeenCalled();
  });

  it('selectHf fetches the readme when the model has no inline description', async () => {
    mockHfService.getFiles.mockReturnValue(of([]));
    mockHfService.getReadme.mockReturnValue(of('<p>readme</p>'));
    const fixture = await createFixture();
    const c = fixture.componentInstance;

    c.selectHf({ id: 'user/repo', modelId: 'user/repo', downloads: 0, tags: [] });
    await fixture.whenStable();

    expect(mockHfService.getReadme).toHaveBeenCalledWith('user/repo');
    expect(c.hfDescription()).toBe('<p>readme</p>');
    expect(c.hfDescriptionLoading()).toBe(false);
  });

  it('downloadHf enqueues with the file url and per-row overrides', async () => {
    const c = (await createFixture()).componentInstance;
    c.selectedHfRepoId.set('user/repo');
    c.setHfRowType('model.safetensors', 'vae');
    c.downloadHf({ filename: 'model.safetensors', size: 10, url: 'https://hf/m' });
    expect(mockDownloadService.startDownload).toHaveBeenCalledWith(
      'https://hf/m',
      'vae',
      'model.safetensors',
      'huggingface',
      'user/repo',
      '',
    );
  });
});
