import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { debounceTime, skip } from 'rxjs';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { CivitaiImage, ImageResource, ImageService, RecreateResult } from '../../services/image';
import { DownloadService } from '../../services/download';
import { NotificationService } from '../../services/notification';
import { isVideo } from '../../utils/media';
import { hideOnError, showOnLoad } from '../../utils/media-events';

const RECREATE_ERROR_KEYS: Record<string, string> = {
  no_metadata: 'images.error.no_metadata',
  image_not_found: 'images.error.not_found',
  provider_unavailable: 'images.error.provider_unavailable',
};

/**
 * Browse CivitAI's image feed and rebuild the workflow behind an image.
 *
 * There is no search box on purpose: `/api/v1/images` has no free-text query parameter —
 * one is silently ignored — so the feed is driven by filters alone.
 *
 * Recreation happens entirely from the API payload. CivitAI re-encodes uploads to JPEG,
 * so the graph embedded in the original PNG is gone, but `meta.comfy` carries it anyway
 * for ComfyUI-generated images. Everything else is mapped onto a template graph.
 */
@Component({
  selector: 'app-images',
  imports: [CommonModule, FormsModule, TranslatePipe],
  templateUrl: './images.html',
  styleUrl: './images.scss',
})
export class Images {
  private readonly imageService = inject(ImageService);
  private readonly downloadService = inject(DownloadService);
  private readonly notifService = inject(NotificationService);
  private readonly translate = inject(TranslateService);
  private readonly destroyRef = inject(DestroyRef);

  readonly sortOptions = [
    { label: 'images.sort.most_reactions', value: 'Most Reactions' },
    { label: 'images.sort.most_comments', value: 'Most Comments' },
    { label: 'images.sort.newest', value: 'Newest' },
  ];
  readonly periodOptions = [
    { label: 'download_search.period.all_time', value: 'AllTime' },
    { label: 'download_search.period.year', value: 'Year' },
    { label: 'download_search.period.month', value: 'Month' },
    { label: 'download_search.period.week', value: 'Week' },
    { label: 'download_search.period.day', value: 'Day' },
  ];
  readonly nsfwOptions = [
    { label: 'images.nsfw.none', value: 'None' },
    { label: 'images.nsfw.soft', value: 'Soft' },
    { label: 'images.nsfw.mature', value: 'Mature' },
    { label: 'images.nsfw.x', value: 'X' },
  ];
  readonly typeOptions = [
    { label: 'images.type.image', value: 'image' },
    { label: 'images.type.video', value: 'video' },
  ];
  readonly baseModelOptions = [
    'SD 1.5',
    'SDXL 1.0',
    'Pony',
    'Illustrious',
    'Flux.1 D',
    'Flux.1 Kontext',
    'Qwen',
    'Krea 2',
  ];

  sort = signal('Most Reactions');
  period = signal('Week');
  nsfw = signal('None');
  baseModel = signal('');
  mediaType = signal('image');
  /** Two thirds of the feed has no usable metadata; hide it unless asked. */
  recreatableOnly = signal(true);

  results = signal<CivitaiImage[]>([]);
  selected = signal<CivitaiImage | null>(null);

  searching = signal(false);
  searchError = signal('');
  loadingMore = signal(false);
  hasMore = signal(false);

  recreating = signal(false);
  recreated = signal<RecreateResult | null>(null);
  recreateError = signal('');
  downloadingResource = signal<string | null>(null);

  private readonly cursor = signal('');

  readonly filteredResults = computed(() => {
    const items = this.results();
    return this.recreatableOnly() ? items.filter((i) => i.recreatable !== '') : items;
  });

  readonly hiddenCount = computed(() => this.results().length - this.filteredResults().length);

  /** Generation parameters worth showing, in a stable order. */
  readonly selectedParams = computed(() => {
    const meta = this.selected()?.meta;
    if (!meta) return [];
    const rows: { key: string; value: string }[] = [];
    // `meta` is an open index signature, so a value can legitimately be an object or an
    // array (CivitAI adds keys without notice). Only primitives are rendered — stringifying
    // the rest would print "[object Object]" at the user (typescript:S6551).
    const push = (key: string, value: unknown) => {
      if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
        if (value !== '') rows.push({ key, value: String(value) });
      }
    };
    push('images.param.model', meta['Model']);
    push('images.param.sampler', meta.sampler);
    push('images.param.scheduler', meta.scheduler);
    push('images.param.steps', meta.steps);
    push('images.param.cfg', meta.cfgScale);
    push('images.param.seed', meta.seed);
    push('images.param.clip_skip', meta.clipSkip);
    return rows;
  });

  readonly missingResources = computed(() =>
    (this.recreated()?.resources ?? []).filter((r) => r.status === 'missing'),
  );

  private readonly filterParams = computed(() => ({
    sort: this.sort(),
    period: this.period(),
    nsfw: this.nsfw(),
    baseModel: this.baseModel(),
    mediaType: this.mediaType(),
  }));

  constructor() {
    toObservable(this.filterParams)
      .pipe(skip(1), debounceTime(300), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.search());
    // The feed needs no query, so it can load straight away.
    this.search();
  }

  search() {
    this.searching.set(true);
    this.results.set([]);
    this.select(null);
    this.cursor.set('');
    this.hasMore.set(false);
    this.searchError.set('');
    this.imageService
      .search(this.searchParams(''))
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (r) => {
          this.results.set(r.items);
          this.cursor.set(r.metadata?.nextCursor ?? '');
          this.hasMore.set(!!r.metadata?.nextCursor);
          this.searching.set(false);
          const first = this.filteredResults()[0];
          if (first) this.select(first);
        },
        error: (err: HttpErrorResponse) => {
          this.searchError.set(this.errorText(err, 'images.error.search_failed'));
          this.searching.set(false);
        },
      });
  }

  loadMore() {
    this.loadingMore.set(true);
    this.imageService
      .search(this.searchParams(this.cursor()))
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (r) => {
          this.results.update((prev) => [...prev, ...r.items]);
          this.cursor.set(r.metadata?.nextCursor ?? '');
          this.hasMore.set(!!r.metadata?.nextCursor);
          this.loadingMore.set(false);
        },
        error: (err: HttpErrorResponse) => {
          this.notifService.show('error', this.errorText(err, 'images.error.search_failed'));
          this.loadingMore.set(false);
        },
      });
  }

  select(image: CivitaiImage | null) {
    this.selected.set(image);
    // The recreation result belongs to the previously selected image.
    this.recreated.set(null);
    this.recreateError.set('');
  }

  recreate() {
    const image = this.selected();
    if (!image || image.recreatable === '') return;
    this.recreating.set(true);
    this.recreateError.set('');
    this.imageService
      .recreate(image.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          this.recreated.set(result);
          this.recreating.set(false);
          this.notifService.show(
            'success',
            this.translate.instant('images.notify.recreated', { name: result.workflow.name }),
          );
        },
        error: (err: HttpErrorResponse) => {
          this.recreateError.set(this.errorText(err, 'images.error.recreate_failed'));
          this.recreating.set(false);
        },
      });
  }

  downloadResource(resource: ImageResource) {
    if (!resource.download_url || !resource.filename) return;
    this.downloadingResource.set(this.resourceKey(resource));
    this.downloadService
      .startDownload(
        resource.download_url,
        resource.model_type ?? 'checkpoints',
        resource.filename,
        'civitai',
        resource.model_version_id,
        resource.base_model ?? '',
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.downloadingResource.set(null);
          this.notifService.show(
            'success',
            this.translate.instant('images.notify.download_queued', {
              name: resource.filename,
            }),
          );
        },
        error: (err: HttpErrorResponse) => {
          this.downloadingResource.set(null);
          this.notifService.show('error', this.errorText(err, 'images.error.download_failed'));
        },
      });
  }

  /** Stable identity for a resource row — names are not unique, hashes may be empty. */
  resourceKey(resource: ImageResource): string {
    return `${resource.kind}:${resource.name}:${resource.hash}:${resource.model_version_id}`;
  }

  resourceLabel(resource: ImageResource): string {
    return resource.name || resource.filename || resource.model_version_id || resource.kind;
  }

  isVideoItem(image: CivitaiImage): boolean {
    return image.type === 'video' || isVideo(image.url);
  }

  onImgLoad(event: Event) {
    showOnLoad(event);
  }

  onImgError(event: Event) {
    hideOnError(event);
  }

  private searchParams(cursor: string) {
    return {
      sort: this.sort(),
      period: this.period(),
      nsfw: this.nsfw(),
      baseModel: this.baseModel(),
      type: this.mediaType(),
      cursor,
      limit: 100,
    };
  }

  private errorText(err: HttpErrorResponse, fallbackKey: string): string {
    const code = err.error?.error ?? '';
    const key = RECREATE_ERROR_KEYS[code];
    if (key) return this.translate.instant(key);
    return code || err.message || this.translate.instant(fallbackKey);
  }
}
