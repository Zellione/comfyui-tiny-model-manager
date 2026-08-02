import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { EMPTY, of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { WorkflowsBrowse } from './workflows-browse';
import { WorkflowStoreService } from '../../services/workflow-store';
import { NotificationService } from '../../services/notification';
import { TagService } from '../../services/tags';
import { CivitaiModel, CivitaiVersion } from '../../services/civitai';

const mockStore = {
  search: vi.fn(),
  download: vi.fn(),
};
const mockNotifService = { show: vi.fn() };
const mockTagService = { searchTags: vi.fn().mockReturnValue(EMPTY) };

function makeVersion(id = 456, overrides: Partial<CivitaiVersion> = {}): CivitaiVersion {
  return {
    id,
    name: 'v1.0',
    baseModel: 'Flux.1 D',
    downloadUrl: '',
    trainedWords: [],
    files: [],
    images: [{ url: 'https://img/a.jpg', type: 'image' }],
    ...overrides,
  };
}

function makeModel(overrides: Partial<CivitaiModel> = {}): CivitaiModel {
  return {
    id: 123,
    name: 'Cool Pack',
    type: 'Workflows',
    description: '',
    tags: ['comfyui', 'tool'],
    modelVersions: [makeVersion()],
    creator: { username: 'me' },
    stats: { downloadCount: 5, thumbsUpCount: 0, thumbsDownCount: 0 },
    ...overrides,
  };
}

function searchResult(items: CivitaiModel[], extra: Record<string, unknown> = {}) {
  return { items, metadata: {}, installed_version_ids: [], ...extra };
}

async function createFixture() {
  await TestBed.configureTestingModule({
    imports: [WorkflowsBrowse],
    providers: [
      { provide: WorkflowStoreService, useValue: mockStore },
      { provide: NotificationService, useValue: mockNotifService },
      { provide: TagService, useValue: mockTagService },
      provideTranslateServiceForTests(),
    ],
  }).compileComponents();
  return TestBed.createComponent(WorkflowsBrowse);
}

async function createComponent() {
  return (await createFixture()).componentInstance;
}

/** Render, optionally after a search, so the template itself is exercised. */
async function render(searchFirst = true) {
  const fixture = await createFixture();
  if (searchFirst) fixture.componentInstance.search();
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
  return fixture;
}

describe('WorkflowsBrowse', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStore.search.mockReturnValue(of(searchResult([])));
    mockStore.download.mockReturnValue(of({ entry_id: 1, workflows: [] }));
  });

  it('starts with no search performed', async () => {
    const c = await createComponent();
    expect(c.hasSearched()).toBe(false);
    expect(c.results()).toEqual([]);
  });

  it('stores results and selects the first one', async () => {
    const model = makeModel();
    mockStore.search.mockReturnValue(of(searchResult([model], { metadata: { nextCursor: 'n1' } })));
    const c = await createComponent();
    c.search();
    expect(c.results()).toEqual([model]);
    expect(c.selectedModel()).toEqual(model);
    expect(c.hasMore()).toBe(true);
  });

  it('records installed version ids from the search payload', async () => {
    mockStore.search.mockReturnValue(
      of(searchResult([makeModel()], { installed_version_ids: ['456'] })),
    );
    const c = await createComponent();
    c.search();
    expect(c.isInstalled(makeVersion(456))).toBe(true);
    expect(c.isInstalled(makeVersion(999))).toBe(false);
  });

  it('sets searchError on failure without clearing hasSearched', async () => {
    mockStore.search.mockReturnValue(
      throwError(() => new HttpErrorResponse({ error: { error: 'provider_unavailable' } })),
    );
    const c = await createComponent();
    c.search();
    expect(c.searchError()).toBe('provider_unavailable');
    expect(c.searching()).toBe(false);
    expect(c.hasSearched()).toBe(true);
  });

  it('appends results on load more', async () => {
    const first = makeModel({ id: 1 });
    const second = makeModel({ id: 2 });
    mockStore.search.mockReturnValue(of(searchResult([first], { metadata: { nextCursor: 'c1' } })));
    const c = await createComponent();
    c.search();
    mockStore.search.mockReturnValue(of(searchResult([second])));
    c.loadMore();
    expect(c.results().map((m) => m.id)).toEqual([1, 2]);
    expect(c.hasMore()).toBe(false);
  });

  it('reports an empty load-more page as an error', async () => {
    mockStore.search.mockReturnValue(of(searchResult([makeModel()])));
    const c = await createComponent();
    c.search();
    mockStore.search.mockReturnValue(of(searchResult([])));
    c.loadMore();
    expect(c.loadMoreError()).toBeTruthy();
    expect(mockNotifService.show).toHaveBeenCalledWith('error', expect.any(String));
  });

  it('sets loadMoreError when load more fails', async () => {
    mockStore.search.mockReturnValue(of(searchResult([makeModel()])));
    const c = await createComponent();
    c.search();
    mockStore.search.mockReturnValue(
      throwError(() => new HttpErrorResponse({ error: { error: 'boom' } })),
    );
    c.loadMore();
    expect(c.loadMoreError()).toBe('boom');
    expect(c.loadingMore()).toBe(false);
  });

  it('filters extra tags client-side (CivitAI only applies the first)', async () => {
    const both = makeModel({ id: 1, tags: ['comfyui', 'tool'] });
    const onlyFirst = makeModel({ id: 2, tags: ['comfyui'] });
    mockStore.search.mockReturnValue(of(searchResult([both, onlyFirst])));
    const c = await createComponent();
    c.search();
    c.addTag('comfyui');
    c.addTag('tool');
    expect(c.filteredResults().map((m) => m.id)).toEqual([1]);
  });

  it('collects tags from every result for the autocomplete', async () => {
    mockStore.search.mockReturnValue(
      of(searchResult([makeModel({ id: 1, tags: ['a'] }), makeModel({ id: 2, tags: ['a', 'b'] })])),
    );
    const c = await createComponent();
    c.search();
    expect(c.allResultTags()).toEqual(['a', 'b']);
  });

  it('ignores duplicate and blank tags, and clears them', async () => {
    const c = await createComponent();
    c.addTag('x');
    c.addTag('x');
    c.addTag('  ');
    expect(c.tagFilter()).toEqual(['x']);
    c.removeTag('x');
    expect(c.tagFilter()).toEqual([]);
    c.addTag('y');
    c.clearTags();
    expect(c.tagFilter()).toEqual([]);
  });

  it('marks a version installed after a successful download', async () => {
    mockStore.download.mockReturnValue(of({ entry_id: 1, workflows: [{ id: 1 }, { id: 2 }] }));
    const c = await createComponent();
    const model = makeModel();
    c.download(model, makeVersion(456));
    expect(c.isInstalled(makeVersion(456))).toBe(true);
    expect(c.downloadingVersionId()).toBeNull();
    expect(mockNotifService.show).toHaveBeenCalledWith('success', expect.any(String));
  });

  it.each([
    ['no_workflow_json', 'This download contains no ComfyUI workflow.'],
    ['corrupt_archive', 'The downloaded archive could not be read.'],
    ['archive_too_large', 'The archive is too large to store.'],
    ['provider_unavailable', 'CivitAI is unreachable right now.'],
  ])('maps the %s download error to a message', async (code, expected) => {
    mockStore.download.mockReturnValue(
      throwError(() => new HttpErrorResponse({ error: { error: code } })),
    );
    const c = await createComponent();
    c.download(makeModel(), makeVersion());
    expect(mockNotifService.show).toHaveBeenCalledWith('error', expected);
    expect(c.downloadingVersionId()).toBeNull();
  });

  it('falls back to a generic message for an unknown error code', async () => {
    mockStore.download.mockReturnValue(throwError(() => new HttpErrorResponse({ error: {} })));
    const c = await createComponent();
    c.download(makeModel(), makeVersion());
    expect(mockNotifService.show).toHaveBeenCalledWith('error', 'Download failed.');
  });

  it('picks the first non-video image as the row thumbnail', async () => {
    const c = await createComponent();
    const model = makeModel({
      modelVersions: [
        makeVersion(1, {
          images: [
            { url: 'https://img/a.mp4', type: 'video' },
            { url: 'https://img/b.jpg', type: 'image' },
          ],
        }),
      ],
    });
    expect(c.thumb(model)).toBe('https://img/b.jpg');
    expect(c.isVideoOnly(model)).toBe(false);
  });

  it('flags a video-only model', async () => {
    const c = await createComponent();
    const model = makeModel({
      modelVersions: [makeVersion(1, { images: [{ url: 'https://img/a.mp4', type: 'video' }] })],
    });
    expect(c.thumb(model)).toBe('');
    expect(c.isVideoOnly(model)).toBe(true);
  });

  it('exposes gallery helpers and the source url', async () => {
    const c = await createComponent();
    const model = makeModel();
    expect(c.galleryImages(model)).toEqual(['https://img/a.jpg']);
    expect(c.currentGalleryUrl(model)).toBe('https://img/a.jpg');
    c.setGalleryIndex(5);
    expect(c.currentGalleryUrl(model)).toBe('');
    expect(c.modelBaseModel(model)).toBe('Flux.1 D');
    expect(c.sourceUrl(model)).toBe('https://civitai.com/models/123');
  });

  it('select resets the gallery index', async () => {
    const c = await createComponent();
    c.setGalleryIndex(3);
    c.select(makeModel());
    expect(c.galleryIndex()).toBe(0);
  });

  it('toggles image visibility on load and error', async () => {
    const c = await createComponent();
    const img = document.createElement('img');
    c.onImgLoad({ target: img } as unknown as Event);
    expect(img.style.display).toBe('block');
    c.onImgError({ target: img } as unknown as Event);
    expect(img.style.display).toBe('none');
  });

  describe('template', () => {
    it('shows the get-started prompt before any search', async () => {
      const el = (await render(false)).nativeElement;
      expect(el.querySelector('.detail-empty')?.textContent).toContain('Search CivitAI');
      expect(el.querySelector('.split-view')).toBeNull();
    });

    it('shows the no-results state for an empty search', async () => {
      const el = (await render()).nativeElement;
      expect(el.querySelector('.detail-empty')).toBeTruthy();
      expect(el.querySelector('.split-view')).toBeNull();
    });

    it('keeps the search bar visible when the search fails', async () => {
      mockStore.search.mockReturnValue(
        throwError(() => new HttpErrorResponse({ error: { error: 'provider_unavailable' } })),
      );
      const el = (await render()).nativeElement;
      expect(el.querySelector('.search-bar')).toBeTruthy();
      expect(el.querySelector('.detail-empty')?.textContent).toContain('provider_unavailable');
    });

    it('renders the split view with a row per result and the detail of the first', async () => {
      mockStore.search.mockReturnValue(
        of(searchResult([makeModel({ id: 1 }), makeModel({ id: 2 })])),
      );
      const el = (await render()).nativeElement;
      expect(el.querySelectorAll('.list-row')).toHaveLength(2);
      expect(el.querySelector('.detail-title')?.textContent).toContain('Cool Pack');
      expect(el.querySelector('.meta-author')?.textContent).toContain('me');
      expect(el.querySelector('.source-link')?.getAttribute('href')).toBe(
        'https://civitai.com/models/1',
      );
    });

    it('renders a download button per version and downloads on click', async () => {
      mockStore.search.mockReturnValue(of(searchResult([makeModel()])));
      const el = (await render()).nativeElement;
      expect(el.querySelectorAll('.version-row')).toHaveLength(1);
      el.querySelector('.version-download').click();
      expect(mockStore.download).toHaveBeenCalledWith(123, 456);
    });

    it('marks an already-downloaded version in the version list', async () => {
      mockStore.search.mockReturnValue(
        of(searchResult([makeModel()], { installed_version_ids: ['456'] })),
      );
      const el = (await render()).nativeElement;
      expect(el.querySelector('.badge-installed')?.textContent).toContain('Downloaded');
    });

    it('selects another result when its row is clicked', async () => {
      mockStore.search.mockReturnValue(
        of(searchResult([makeModel({ id: 1 }), makeModel({ id: 2, name: 'Second' })])),
      );
      const fixture = await render();
      fixture.nativeElement.querySelectorAll('.list-row')[1].click();
      fixture.detectChanges();
      expect(fixture.componentInstance.selectedModel()?.id).toBe(2);
      expect(fixture.nativeElement.querySelector('.detail-title')?.textContent).toContain('Second');
    });

    it('shows the video placeholder for a video-only result', async () => {
      mockStore.search.mockReturnValue(
        of(
          searchResult([
            makeModel({
              modelVersions: [
                makeVersion(1, { images: [{ url: 'https://img/a.mp4', type: 'video' }] }),
              ],
            }),
          ]),
        ),
      );
      const el = (await render()).nativeElement;
      expect(el.querySelector('.row-thumb .video-only-icon')).toBeTruthy();
    });

    it('renders the tag chips of the active filter', async () => {
      mockStore.search.mockReturnValue(of(searchResult([makeModel()])));
      const fixture = await render();
      fixture.componentInstance.addTag('comfyui');
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('.active-tag')?.textContent).toContain('comfyui');
    });
  });
});
