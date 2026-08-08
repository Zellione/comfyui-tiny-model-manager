import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { EMPTY, of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { Images } from './images';
import { CivitaiImage, ImageResource, ImageService, RecreateResult } from '../../services/image';
import { DownloadService } from '../../services/download';
import { NotificationService } from '../../services/notification';

const mockImageService = {
  search: vi.fn(),
  get: vi.fn(),
  recreate: vi.fn(),
  resolveResources: vi.fn(),
};
const mockDownloadService = {
  startDownload: vi.fn(),
  activeTasks$: of([]),
  completedTasks$: EMPTY,
};
const mockNotifService = { show: vi.fn() };

function makeImage(overrides: Partial<CivitaiImage> = {}): CivitaiImage {
  return {
    id: 1,
    url: 'https://image.civitai.com/a.jpeg',
    width: 512,
    height: 768,
    type: 'image',
    baseModel: 'SDXL 1.0',
    username: 'someone',
    meta: { prompt: 'a cat', steps: 20, cfgScale: 7, sampler: 'Euler a', seed: 5 },
    recreatable: 'params',
    ...overrides,
  };
}

function searchResult(items: CivitaiImage[], nextCursor?: string) {
  return { items, metadata: nextCursor ? { nextCursor } : {} };
}

function makeResource(overrides: Partial<ImageResource> = {}): ImageResource {
  return {
    kind: 'lora',
    name: 'Sparkle',
    weight: 0.7,
    hash: 'bbbbbbbbbb',
    model_version_id: '9',
    status: 'missing',
    filename: 'sparkle.safetensors',
    download_url: 'https://civitai.com/api/download/models/9',
    model_type: 'loras',
    base_model: 'SDXL 1.0',
    ...overrides,
  };
}

function makeRecreateResult(overrides: Partial<RecreateResult> = {}): RecreateResult {
  return {
    entry_id: 1,
    workflow: {
      id: 2,
      entry_id: 1,
      name: 'CivitAI image 1',
      local_path: 'x/0/a.json',
      version_id: '',
      version_name: '',
      node_count: 14,
    },
    source: 'params',
    base_model: 'SDXL 1.0',
    template_warning: false,
    resources: [],
    ...overrides,
  };
}

async function createFixture() {
  await TestBed.configureTestingModule({
    imports: [Images],
    providers: [
      { provide: ImageService, useValue: mockImageService },
      { provide: DownloadService, useValue: mockDownloadService },
      { provide: NotificationService, useValue: mockNotifService },
      provideTranslateServiceForTests(),
    ],
  }).compileComponents();
  return TestBed.createComponent(Images);
}

async function createComponent() {
  return (await createFixture()).componentInstance;
}

/** Render so the template itself is exercised, not just the component logic. */
async function render() {
  const fixture = await createFixture();
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
  return fixture;
}

describe('Images', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    TestBed.resetTestingModule();
    mockImageService.search.mockReturnValue(of(searchResult([])));
    mockImageService.recreate.mockReturnValue(of(makeRecreateResult()));
    mockDownloadService.startDownload.mockReturnValue(of({ task_id: 't1' }));
  });

  describe('search', () => {
    it('loads the feed on construction — the API needs no query', async () => {
      const image = makeImage();
      mockImageService.search.mockReturnValue(of(searchResult([image], 'n1')));
      const c = await createComponent();
      expect(mockImageService.search).toHaveBeenCalled();
      expect(c.results()).toEqual([image]);
      expect(c.hasMore()).toBe(true);
    });

    it('selects the first recreatable result', async () => {
      const bare = makeImage({ id: 1, recreatable: '' });
      const usable = makeImage({ id: 2, recreatable: 'graph' });
      mockImageService.search.mockReturnValue(of(searchResult([bare, usable])));
      const c = await createComponent();
      expect(c.selected()?.id).toBe(2);
    });

    it('records a search failure without clearing the view state', async () => {
      mockImageService.search.mockReturnValue(
        throwError(() => new HttpErrorResponse({ error: { error: 'provider_unavailable' } })),
      );
      const c = await createComponent();
      expect(c.searchError()).toBe('CivitAI is unreachable right now.');
      expect(c.searching()).toBe(false);
    });

    it('appends results when loading more', async () => {
      const first = makeImage({ id: 1 });
      mockImageService.search.mockReturnValue(of(searchResult([first], 'n1')));
      const c = await createComponent();
      const second = makeImage({ id: 2 });
      mockImageService.search.mockReturnValue(of(searchResult([second])));
      c.loadMore();
      expect(c.results().map((i) => i.id)).toEqual([1, 2]);
      expect(c.hasMore()).toBe(false);
    });

    it('reports a load-more failure as a toast, not a page error', async () => {
      mockImageService.search.mockReturnValue(of(searchResult([makeImage()], 'n1')));
      const c = await createComponent();
      mockImageService.search.mockReturnValue(
        throwError(() => new HttpErrorResponse({ error: {}, status: 500 })),
      );
      c.loadMore();
      expect(mockNotifService.show).toHaveBeenCalledWith('error', expect.any(String));
      expect(c.searchError()).toBe('');
      expect(c.loadingMore()).toBe(false);
    });

    it('sends the active filters', async () => {
      const c = await createComponent();
      mockImageService.search.mockClear();
      c.sort.set('Newest');
      c.nsfw.set('Soft');
      c.baseModel.set('Pony');
      c.mediaType.set('video');
      c.search();
      expect(mockImageService.search).toHaveBeenCalledWith(
        expect.objectContaining({
          sort: 'Newest',
          nsfw: 'Soft',
          baseModel: 'Pony',
          type: 'video',
        }),
      );
    });
  });

  describe('recreatable filter', () => {
    it('hides images without metadata by default and counts them', async () => {
      mockImageService.search.mockReturnValue(
        of(searchResult([makeImage({ id: 1 }), makeImage({ id: 2, recreatable: '' })])),
      );
      const c = await createComponent();
      expect(c.recreatableOnly()).toBe(true);
      expect(c.filteredResults().map((i) => i.id)).toEqual([1]);
      expect(c.hiddenCount()).toBe(1);
    });

    it('shows everything when unchecked', async () => {
      mockImageService.search.mockReturnValue(
        of(searchResult([makeImage({ id: 1 }), makeImage({ id: 2, recreatable: '' })])),
      );
      const c = await createComponent();
      c.recreatableOnly.set(false);
      expect(c.filteredResults()).toHaveLength(2);
      expect(c.hiddenCount()).toBe(0);
    });
  });

  describe('selectedParams', () => {
    it('lists the populated parameters only', async () => {
      mockImageService.search.mockReturnValue(of(searchResult([makeImage()])));
      const c = await createComponent();
      const keys = c.selectedParams().map((r) => r.key);
      expect(keys).toEqual([
        'images.param.sampler',
        'images.param.steps',
        'images.param.cfg',
        'images.param.seed',
      ]);
    });

    it('skips non-primitive values instead of printing [object Object]', async () => {
      // CivitAI adds meta keys without notice; some are objects or arrays.
      mockImageService.search.mockReturnValue(
        of(
          searchResult([
            makeImage({
              meta: {
                Model: { name: 'nested' } as unknown as string,
                sampler: 'Euler a',
                steps: 0,
              },
            }),
          ]),
        ),
      );
      const c = await createComponent();
      const rows = c.selectedParams();
      expect(rows.map((r) => r.key)).toEqual(['images.param.sampler', 'images.param.steps']);
      expect(rows.some((r) => r.value.includes('[object'))).toBe(false);
      // 0 is a real value and must survive the emptiness check.
      expect(rows.find((r) => r.key === 'images.param.steps')?.value).toBe('0');
    });

    it('is empty when the image has no metadata', async () => {
      mockImageService.search.mockReturnValue(
        of(searchResult([makeImage({ recreatable: '', meta: null })])),
      );
      const c = await createComponent();
      c.recreatableOnly.set(false);
      c.select(c.results()[0]);
      expect(c.selectedParams()).toEqual([]);
    });
  });

  describe('recreate', () => {
    it('stores the result and notifies', async () => {
      mockImageService.search.mockReturnValue(of(searchResult([makeImage()])));
      const c = await createComponent();
      c.recreate();
      expect(mockImageService.recreate).toHaveBeenCalledWith(1);
      expect(c.recreated()?.workflow.node_count).toBe(14);
      expect(mockNotifService.show).toHaveBeenCalledWith('success', expect.any(String));
    });

    it('does nothing for an image with no metadata', async () => {
      mockImageService.search.mockReturnValue(of(searchResult([makeImage({ recreatable: '' })])));
      const c = await createComponent();
      c.recreatableOnly.set(false);
      c.select(c.results()[0]);
      c.recreate();
      expect(mockImageService.recreate).not.toHaveBeenCalled();
    });

    it('maps a backend error code to a translated message', async () => {
      mockImageService.search.mockReturnValue(of(searchResult([makeImage()])));
      const c = await createComponent();
      mockImageService.recreate.mockReturnValue(
        throwError(() => new HttpErrorResponse({ error: { error: 'no_metadata' } })),
      );
      c.recreate();
      expect(c.recreateError()).toBe('This image has no usable generation metadata.');
      expect(c.recreating()).toBe(false);
    });

    it('clears the previous result when another image is selected', async () => {
      mockImageService.search.mockReturnValue(
        of(searchResult([makeImage({ id: 1 }), makeImage({ id: 2 })])),
      );
      const c = await createComponent();
      c.recreate();
      expect(c.recreated()).not.toBeNull();
      c.select(c.results()[1]);
      expect(c.recreated()).toBeNull();
    });

    it('exposes the missing resources separately', async () => {
      mockImageService.search.mockReturnValue(of(searchResult([makeImage()])));
      mockImageService.recreate.mockReturnValue(
        of(
          makeRecreateResult({
            resources: [
              makeResource(),
              makeResource({ status: 'installed', name: 'Base', hash: 'aaaaaaaaaa' }),
            ],
          }),
        ),
      );
      const c = await createComponent();
      c.recreate();
      expect(c.missingResources()).toHaveLength(1);
    });
  });

  describe('downloadResource', () => {
    it('enqueues through the normal download manager', async () => {
      const c = await createComponent();
      c.downloadResource(makeResource());
      expect(mockDownloadService.startDownload).toHaveBeenCalledWith(
        'https://civitai.com/api/download/models/9',
        'loras',
        'sparkle.safetensors',
        'civitai',
        '9',
        'SDXL 1.0',
      );
      expect(mockNotifService.show).toHaveBeenCalledWith('success', expect.any(String));
      expect(c.downloadingResource()).toBeNull();
    });

    it('ignores a resource with nothing to download', async () => {
      const c = await createComponent();
      c.downloadResource(makeResource({ download_url: undefined }));
      expect(mockDownloadService.startDownload).not.toHaveBeenCalled();
    });

    it('reports a failure and clears the busy flag', async () => {
      const c = await createComponent();
      mockDownloadService.startDownload.mockReturnValue(
        throwError(() => new HttpErrorResponse({ error: {}, status: 500 })),
      );
      c.downloadResource(makeResource());
      expect(mockNotifService.show).toHaveBeenCalledWith('error', expect.any(String));
      expect(c.downloadingResource()).toBeNull();
    });
  });

  describe('helpers', () => {
    it('resourceKey is stable and distinguishes same-named resources', async () => {
      const c = await createComponent();
      const a = makeResource({ hash: 'aaaaaaaaaa' });
      const b = makeResource({ hash: 'bbbbbbbbbb' });
      expect(c.resourceKey(a)).toBe(c.resourceKey({ ...a }));
      expect(c.resourceKey(a)).not.toBe(c.resourceKey(b));
    });

    it('resourceLabel falls back through name, filename, version id', async () => {
      const c = await createComponent();
      expect(c.resourceLabel(makeResource())).toBe('Sparkle');
      expect(c.resourceLabel(makeResource({ name: '' }))).toBe('sparkle.safetensors');
      expect(c.resourceLabel(makeResource({ name: '', filename: '' }))).toBe('9');
    });

    it('detects videos by type and by url', async () => {
      const c = await createComponent();
      expect(c.isVideoItem(makeImage({ type: 'video' }))).toBe(true);
      expect(c.isVideoItem(makeImage({ type: undefined, url: 'https://x/a.mp4' }))).toBe(true);
      expect(c.isVideoItem(makeImage())).toBe(false);
    });

    it('detailMediaUrls follows the selection and is empty with none', async () => {
      const c = await createComponent();
      expect(c.detailMediaUrls()).toEqual([]);

      c.selected.set(makeImage({ url: 'https://x/frog.jpeg' }));
      expect(c.detailMediaUrls()).toEqual(['https://x/frog.jpeg']);
    });

    it('detailMediaUrls keeps a stable reference while the selection is unchanged', async () => {
      const c = await createComponent();
      c.selected.set(makeImage());
      expect(c.detailMediaUrls()).toBe(c.detailMediaUrls());
    });

    it('reveals an image once it loads and hides it on error', async () => {
      const c = await createComponent();
      const img = document.createElement('img');
      c.onImgLoad({ target: img } as unknown as Event);
      expect(img.style.display).toBe('block');
      c.onImgError({ target: img } as unknown as Event);
      expect(img.style.display).toBe('none');
    });
  });

  describe('template', () => {
    it('renders a row per result and the detail of the selected one', async () => {
      mockImageService.search.mockReturnValue(
        of(searchResult([makeImage({ id: 1 }), makeImage({ id: 2 })])),
      );
      const el = (await render()).nativeElement;
      expect(el.querySelectorAll('.list-row')).toHaveLength(2);
      expect(el.querySelector('.detail-title')?.textContent).toContain('1');
      expect(el.querySelector('.param-grid')).toBeTruthy();
    });

    it('badges each row by its recreation path', async () => {
      mockImageService.search.mockReturnValue(
        of(
          searchResult([
            makeImage({ id: 1, recreatable: 'graph' }),
            makeImage({ id: 2, recreatable: 'params' }),
            makeImage({ id: 3, recreatable: '' }),
          ]),
        ),
      );
      const fixture = await render();
      fixture.componentInstance.recreatableOnly.set(false);
      fixture.detectChanges();
      const badges = fixture.nativeElement.querySelectorAll('.list-row .badge');
      expect(badges[0].textContent.trim()).toBe('Graph');
      expect(badges[1].textContent.trim()).toBe('Params');
      expect(badges[2].textContent.trim()).toBe('No metadata');
    });

    it('disables Recreate for an image with no metadata', async () => {
      mockImageService.search.mockReturnValue(of(searchResult([makeImage({ recreatable: '' })])));
      const fixture = await render();
      fixture.componentInstance.recreatableOnly.set(false);
      fixture.detectChanges();
      fixture.componentInstance.select(fixture.componentInstance.results()[0]);
      fixture.detectChanges();
      const btn = fixture.nativeElement.querySelector('.recreate-btn') as HTMLButtonElement;
      expect(btn.disabled).toBe(true);
      expect(fixture.nativeElement.querySelector('.recreate-disabled')).toBeTruthy();
    });

    it('recreates when the button is clicked and lists the resources', async () => {
      mockImageService.search.mockReturnValue(of(searchResult([makeImage()])));
      mockImageService.recreate.mockReturnValue(
        of(
          makeRecreateResult({
            resources: [
              makeResource(),
              makeResource({ status: 'installed', name: 'Base' }),
              makeResource({ status: 'unresolvable', name: 'Ghost' }),
            ],
          }),
        ),
      );
      const fixture = await render();
      (fixture.nativeElement.querySelector('.recreate-btn') as HTMLButtonElement).click();
      fixture.detectChanges();
      expect(mockImageService.recreate).toHaveBeenCalled();
      expect(fixture.nativeElement.querySelectorAll('.resource-row')).toHaveLength(3);
      expect(fixture.nativeElement.querySelector('.recreate-success')).toBeTruthy();
      expect(fixture.nativeElement.querySelector('.resource-note')?.textContent).toContain(
        'Not found on CivitAI',
      );
    });

    it('shows the template caveat for a non-SD base model', async () => {
      mockImageService.search.mockReturnValue(of(searchResult([makeImage()])));
      mockImageService.recreate.mockReturnValue(
        of(makeRecreateResult({ template_warning: true, base_model: 'Flux.1 D' })),
      );
      const fixture = await render();
      fixture.componentInstance.recreate();
      fixture.detectChanges();
      const warning = fixture.nativeElement.querySelector('.recreate-warning');
      expect(warning?.textContent).toContain('Flux.1 D');
    });

    it('queues a download from the resource row', async () => {
      mockImageService.search.mockReturnValue(of(searchResult([makeImage()])));
      mockImageService.recreate.mockReturnValue(
        of(makeRecreateResult({ resources: [makeResource()] })),
      );
      const fixture = await render();
      fixture.componentInstance.recreate();
      fixture.detectChanges();
      (fixture.nativeElement.querySelector('.resource-row button') as HTMLButtonElement).click();
      expect(mockDownloadService.startDownload).toHaveBeenCalled();
    });

    it('shows the empty state when nothing matches', async () => {
      mockImageService.search.mockReturnValue(of(searchResult([])));
      const el = (await render()).nativeElement;
      expect(el.querySelector('.detail-empty')?.textContent).toContain('No images matched');
      expect(el.querySelector('.split-view')).toBeFalsy();
    });

    it('shows the error branch instead of the empty state on failure', async () => {
      mockImageService.search.mockReturnValue(
        throwError(() => new HttpErrorResponse({ error: { error: 'provider_unavailable' } })),
      );
      const el = (await render()).nativeElement;
      expect(el.querySelector('.detail-empty')?.textContent).toContain('unreachable');
    });

    it('renders the hidden-count hint', async () => {
      mockImageService.search.mockReturnValue(
        of(searchResult([makeImage({ id: 1 }), makeImage({ id: 2, recreatable: '' })])),
      );
      const el = (await render()).nativeElement;
      expect(el.querySelector('.hidden-count')?.textContent).toContain('1');
    });

    it('selects a row on click', async () => {
      mockImageService.search.mockReturnValue(
        of(searchResult([makeImage({ id: 1 }), makeImage({ id: 2 })])),
      );
      const fixture = await render();
      const rows = fixture.nativeElement.querySelectorAll('.list-row');
      rows[1].click();
      fixture.detectChanges();
      expect(fixture.componentInstance.selected()?.id).toBe(2);
    });

    it('shows a play icon instead of an image for videos', async () => {
      mockImageService.search.mockReturnValue(
        of(searchResult([makeImage({ type: 'video', url: 'https://x/a.mp4' })])),
      );
      const el = (await render()).nativeElement;
      expect(el.querySelector('.row-thumb .video-only-icon')).toBeTruthy();
      // The detail preview is the shared gallery, which picks the <video> branch
      // from the .mp4 extension.
      const video: HTMLVideoElement = el.querySelector('app-media-gallery .gallery-main video');
      expect(video).toBeTruthy();
      expect(video.getAttribute('src')).toBe('https://x/a.mp4');
    });
  });
});
