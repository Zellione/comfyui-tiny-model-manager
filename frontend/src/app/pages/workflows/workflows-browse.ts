import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { debounceTime, skip } from 'rxjs';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { CivitaiModel, CivitaiVersion } from '../../services/civitai';
import { WorkflowStoreService } from '../../services/workflow-store';
import { NotificationService } from '../../services/notification';
import { TagAutocompleteInput } from '../../components/tag-autocomplete-input/tag-autocomplete-input';
import { SafeHtmlPipe } from '../../utils/safe-html.pipe';
import { isVideo } from '../../utils/media';

/**
 * Browse CivitAI's `Workflows` model type in the same split view the download page uses.
 *
 * Versions come straight from the search payload — unlike model downloads there is no
 * follow-up file listing to fetch, because the backend picks the archive itself and
 * unpacks whatever graphs it holds.
 */
@Component({
  selector: 'app-workflows-browse',
  imports: [CommonModule, FormsModule, TagAutocompleteInput, SafeHtmlPipe, TranslatePipe],
  templateUrl: './workflows-browse.html',
  styleUrl: './workflows-browse.scss',
})
export class WorkflowsBrowse {
  private readonly store = inject(WorkflowStoreService);
  private readonly notifService = inject(NotificationService);
  private readonly translate = inject(TranslateService);
  private readonly destroyRef = inject(DestroyRef);

  readonly sortOptions = [
    { label: 'download_search.sort.most_downloaded', value: 'Most Downloaded' },
    { label: 'download_search.sort.highest_rated', value: 'Highest Rated' },
    { label: 'download_search.sort.newest', value: 'Newest' },
  ];
  readonly periodOptions = [
    { label: 'download_search.period.all_time', value: 'AllTime' },
    { label: 'download_search.period.year', value: 'Year' },
    { label: 'download_search.period.month', value: 'Month' },
    { label: 'download_search.period.week', value: 'Week' },
    { label: 'download_search.period.day', value: 'Day' },
  ];
  readonly baseModelOptions = [
    'SD 1.5',
    'SDXL 1.0',
    'Pony',
    'Illustrious',
    'Flux.1 D',
    'Flux.1 Kontext',
    'Wan Video 2.2 I2V-A14B',
    'Qwen',
  ];

  query = signal('');
  sort = signal('Most Downloaded');
  period = signal('AllTime');
  baseModel = signal('');
  tagFilter = signal<string[]>([]);

  results = signal<CivitaiModel[]>([]);
  selectedModel = signal<CivitaiModel | null>(null);
  galleryIndex = signal(0);
  installedVersionIds = signal<string[]>([]);

  hasSearched = signal(false);
  searching = signal(false);
  searchError = signal('');
  loadingMore = signal(false);
  loadMoreError = signal('');
  hasMore = signal(false);
  downloadingVersionId = signal<number | null>(null);

  private cursor = signal('');

  /** CivitAI applies only the first tag server-side; the rest are filtered here. */
  readonly filteredResults = computed(() => {
    const tags = this.tagFilter();
    const results = this.results();
    if (tags.length <= 1) return results;
    const extra = tags.slice(1);
    return results.filter((m) => extra.every((t) => m.tags?.includes(t)));
  });

  readonly allResultTags = computed(() => [
    ...new Set(this.results().flatMap((m) => m.tags ?? [])),
  ]);

  private readonly serverTag = computed(() => this.tagFilter()[0] ?? '');

  private readonly filterParams = computed(() => ({
    sort: this.sort(),
    period: this.period(),
    baseModel: this.baseModel(),
    serverTag: this.serverTag(),
  }));

  constructor() {
    toObservable(this.filterParams)
      .pipe(skip(1), debounceTime(300), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        if (this.hasSearched()) this.search();
      });
  }

  search() {
    this.hasSearched.set(true);
    this.searching.set(true);
    this.results.set([]);
    this.selectedModel.set(null);
    this.cursor.set('');
    this.hasMore.set(false);
    this.loadMoreError.set('');
    this.searchError.set('');
    this.store.search(this.searchParams('')).subscribe({
      next: (r) => {
        this.results.set(r.items);
        this.cursor.set(r.metadata?.nextCursor ?? '');
        this.hasMore.set(!!r.metadata?.nextCursor);
        this.installedVersionIds.set(r.installed_version_ids);
        this.searching.set(false);
        if (r.items.length > 0) this.select(r.items[0]);
      },
      error: (err: HttpErrorResponse) => {
        this.searchError.set(err.error?.error ?? err.message ?? 'Search failed');
        this.searching.set(false);
      },
    });
  }

  loadMore() {
    const wasError = !!this.loadMoreError();
    this.loadMoreError.set('');
    this.loadingMore.set(true);
    this.store.search(this.searchParams(this.cursor())).subscribe({
      next: (r) => {
        if (r.items.length === 0 && !wasError) {
          const msg = this.translate.instant('download_search.error.no_results');
          this.loadMoreError.set(msg);
          this.notifService.show('error', msg);
        } else {
          this.results.update((prev) => [...prev, ...r.items]);
          this.cursor.set(r.metadata?.nextCursor ?? '');
          this.hasMore.set(!!r.metadata?.nextCursor);
        }
        this.loadingMore.set(false);
      },
      error: (err: HttpErrorResponse) => {
        const msg =
          err.error?.error ??
          err.message ??
          this.translate.instant('download_search.error.request_failed');
        this.loadMoreError.set(msg);
        this.notifService.show('error', msg);
        this.loadingMore.set(false);
      },
    });
  }

  private searchParams(cursor: string) {
    return {
      q: this.query(),
      cursor,
      baseModel: this.baseModel(),
      sort: this.sort(),
      period: this.period(),
      tags: this.tagFilter(),
    };
  }

  select(model: CivitaiModel) {
    this.selectedModel.set(model);
    this.galleryIndex.set(0);
  }

  download(model: CivitaiModel, version: CivitaiVersion) {
    this.downloadingVersionId.set(version.id);
    this.store.download(model.id, version.id).subscribe({
      next: (r) => {
        this.downloadingVersionId.set(null);
        this.installedVersionIds.update((ids) => [...new Set([...ids, String(version.id)])]);
        this.notifService.show(
          'success',
          this.translate.instant('workflows.notify.downloaded', {
            count: r.workflows.length,
            name: model.name,
          }),
        );
      },
      error: (err: HttpErrorResponse) => {
        this.downloadingVersionId.set(null);
        this.notifService.show('error', this.downloadErrorMessage(err));
      },
    });
  }

  /**
   * Map the backend's error codes to a translated message. The 422 case is the one users
   * actually hit: a CivitAI "workflow" whose archive holds no ComfyUI graph at all.
   */
  private downloadErrorMessage(err: HttpErrorResponse): string {
    const code = err.error?.error ?? '';
    const keys: Record<string, string> = {
      no_workflow_json: 'workflows.error.no_workflow_json',
      corrupt_archive: 'workflows.error.corrupt_archive',
      no_download_url: 'workflows.error.no_download_url',
      no_version: 'workflows.error.no_download_url',
      archive_too_large: 'workflows.error.too_large',
      provider_unavailable: 'workflows.error.provider_unavailable',
    };
    const key = keys[code];
    return key
      ? this.translate.instant(key)
      : code || this.translate.instant('workflows.error.download_failed');
  }

  isInstalled(version: CivitaiVersion): boolean {
    return this.installedVersionIds().includes(String(version.id));
  }

  addTag(tag: string) {
    const t = tag.trim();
    if (!t || this.tagFilter().includes(t)) return;
    this.tagFilter.update((tags) => [...tags, t]);
  }

  removeTag(tag: string) {
    this.tagFilter.update((tags) => tags.filter((t) => t !== tag));
  }

  clearTags() {
    this.tagFilter.set([]);
  }

  thumb(model: CivitaiModel): string {
    const images = model.modelVersions?.[0]?.images ?? [];
    return images.find((img) => img.type !== 'video' && !isVideo(img.url))?.url ?? '';
  }

  isVideoOnly(model: CivitaiModel): boolean {
    const images = model.modelVersions?.[0]?.images ?? [];
    return images.length > 0 && images.every((img) => img.type === 'video' || isVideo(img.url));
  }

  galleryImages(model: CivitaiModel): string[] {
    return (model.modelVersions?.[0]?.images ?? [])
      .slice(0, 8)
      .map((i) => i.url)
      .filter(Boolean);
  }

  currentGalleryUrl(model: CivitaiModel): string {
    return this.galleryImages(model)[this.galleryIndex()] ?? '';
  }

  setGalleryIndex(i: number) {
    this.galleryIndex.set(i);
  }

  modelBaseModel(model: CivitaiModel): string {
    return model.modelVersions?.[0]?.baseModel ?? '';
  }

  sourceUrl(model: CivitaiModel): string {
    return `https://civitai.com/models/${model.id}`;
  }

  isVideo = isVideo;

  onImgLoad(event: Event) {
    (event.target as HTMLImageElement).style.display = 'block';
  }

  onImgError(event: Event) {
    (event.target as HTMLImageElement).style.display = 'none';
  }
}
