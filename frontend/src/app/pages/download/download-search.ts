import { Component, signal, inject, computed, DestroyRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { toObservable, takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { skip, debounceTime } from 'rxjs';
import { CivitaiService, CivitaiModel, CivitaiVersion, CivitaiFile } from '../../services/civitai';
import { HuggingFaceService, HfModel } from '../../services/huggingface';
import { ModelType } from '../../utils/model-types';
import { formatSize } from '../../utils/format';
import { isVideo } from '../../utils/media';
import { ModelTypeSelect } from '../../components/model-type-select/model-type-select';
import { BaseModelSelect } from '../../components/base-model-select/base-model-select';
import { TagAutocompleteInput } from '../../components/tag-autocomplete-input/tag-autocomplete-input';
import { SafeHtmlPipe } from '../../utils/safe-html.pipe';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { NotificationService } from '../../services/notification';
import { InstalledFilesService } from '../../services/installed-files';

type Platform = 'civitai' | 'huggingface';

/**
 * The model search section of the download page: the CivitAI/HuggingFace search
 * bar with filters and the results split-view (list + detail). Filename
 * detection, installed-file status, download enqueue, and per-row override
 * helpers are shared with the paste-a-link section via InstalledFilesService.
 */
@Component({
  selector: 'app-download-search',
  imports: [
    CommonModule,
    FormsModule,
    ModelTypeSelect,
    BaseModelSelect,
    TagAutocompleteInput,
    SafeHtmlPipe,
    TranslatePipe,
  ],
  templateUrl: './download-search.html',
  styleUrl: './download-search.scss',
})
export class DownloadSearch {
  private readonly civitaiService = inject(CivitaiService);
  private readonly hfService = inject(HuggingFaceService);
  private readonly notifService = inject(NotificationService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly installed = inject(InstalledFilesService);
  private readonly translate = inject(TranslateService);

  readonly civitaiSortOptions = [
    { label: 'download_search.sort.most_downloaded', value: 'Most Downloaded' },
    { label: 'download_search.sort.highest_rated', value: 'Highest Rated' },
    { label: 'download_search.sort.newest', value: 'Newest' },
  ];
  readonly civitaiPeriodOptions = [
    { label: 'download_search.period.all_time', value: 'AllTime' },
    { label: 'download_search.period.year', value: 'Year' },
    { label: 'download_search.period.month', value: 'Month' },
    { label: 'download_search.period.week', value: 'Week' },
    { label: 'download_search.period.day', value: 'Day' },
  ];
  readonly hfSortOptions = [
    { label: 'download_search.hf_sort.downloads', value: 'downloads' },
    { label: 'download_search.hf_sort.likes', value: 'likes' },
    { label: 'download_search.hf_sort.trending', value: 'trending' },
    { label: 'download_search.hf_sort.recently_updated', value: 'lastModified' },
    { label: 'download_search.hf_sort.recently_created', value: 'createdAt' },
  ];
  readonly formatOptions = [
    { label: 'download_search.format.all', value: '' },
    { label: 'download_search.format.safetensors', value: '.safetensors' },
    { label: 'download_search.format.gguf', value: '.gguf' },
    { label: 'download_search.format.ckpt', value: '.ckpt' },
    { label: 'download_search.format.pt', value: '.pt' },
    { label: 'download_search.format.bin', value: '.bin' },
  ];
  readonly civitaiBaseModelOptions = [
    'SD 1.5',
    'SD 2.1',
    'SDXL 1.0',
    'Pony',
    'Illustrious',
    'Flux.1 D',
    'Flux.1 S',
    'Stable Cascade',
    'SDXL Turbo',
    'Chroma',
    'Qwen',
  ];

  platform = signal<Platform>('civitai');
  query = signal('');
  modelType = signal<ModelType>('checkpoints');

  hfRowTypes = signal<Record<string, ModelType>>({});
  civitaiFileTypes = signal<Record<string, ModelType>>({});

  hfRowBaseModels = signal<Record<string, string>>({});
  civitaiFileBaseModels = signal<Record<string, string>>({});

  hfRowType(name: string): ModelType {
    return this.installed.readOverride(this.hfRowTypes, name, 'checkpoints');
  }
  setHfRowType(name: string, t: ModelType) {
    this.installed.writeOverride(this.hfRowTypes, name, t);
  }

  civitaiFileType(versionId: number, file: CivitaiFile): ModelType {
    return this.installed.readOverride(
      this.civitaiFileTypes,
      this.installed.fileKey(versionId, file),
      'checkpoints',
    );
  }
  setCivitaiFileType(versionId: number, file: CivitaiFile, t: ModelType) {
    this.installed.writeOverride(this.civitaiFileTypes, this.installed.fileKey(versionId, file), t);
  }

  hfRowBaseModel(name: string): string {
    return this.installed.readOverride(this.hfRowBaseModels, name, '');
  }
  setHfRowBaseModel(name: string, v: string) {
    this.installed.writeOverride(this.hfRowBaseModels, name, v);
  }

  civitaiFileBaseModel(versionId: number, file: CivitaiFile): string {
    return this.installed.readOverride(
      this.civitaiFileBaseModels,
      this.installed.fileKey(versionId, file),
      '',
    );
  }
  setCivitaiFileBaseModel(versionId: number, file: CivitaiFile, v: string) {
    this.installed.writeOverride(
      this.civitaiFileBaseModels,
      this.installed.fileKey(versionId, file),
      v,
    );
  }

  civitaiSort = signal('');
  civitaiPeriod = signal('AllTime');
  civitaiBaseModel = signal('');
  hfSort = signal('downloads');
  formatFilter = signal('');
  tagFilter = signal<string[]>([]);
  hasSearched = signal(false);

  civitaiResults = signal<CivitaiModel[]>([]);
  hfResults = signal<HfModel[]>([]);

  filteredCivitaiResults = computed(() => {
    const fmt = this.formatFilter();
    const tags = this.tagFilter();
    let results = this.civitaiResults();
    if (fmt) {
      results = results.filter((m) =>
        m.modelVersions?.some((v) => v.files?.some((f) => f.name.toLowerCase().endsWith(fmt))),
      );
    }
    // Server applies only the first tag; filter the rest client-side using the tags returned per model
    if (tags.length > 1) {
      const extraTags = tags.slice(1);
      results = results.filter((m) => extraTags.every((t) => m.tags?.includes(t)));
    }
    return results;
  });

  filteredHfResults = computed(() => {
    const fmt = this.formatFilter();
    if (!fmt) return this.hfResults();
    return this.hfResults().filter((m) => m.formats?.includes(fmt));
  });

  readonly allResultTags = computed(() => {
    const civitaiTags = this.civitaiResults().flatMap((m) => m.tags ?? []);
    const hfTags = this.hfResults().flatMap((m) => m.tags);
    return [...new Set([...civitaiTags, ...hfTags])];
  });

  // Intermediary so Angular stops propagating when the first tag value is unchanged (adding a 2nd+ tag).
  private readonly civitaiServerTag = computed(() => this.tagFilter()[0] ?? '');

  private readonly filterParams = computed(() => ({
    civitaiSort: this.civitaiSort(),
    civitaiPeriod: this.civitaiPeriod(),
    civitaiBaseModel: this.civitaiBaseModel(),
    hfSort: this.hfSort(),
    formatFilter: this.formatFilter(),
    // civitaiServerTag() not tagFilter() — avoids re-fetch when only client-side extra tags change.
    serverTag: this.platform() === 'civitai' ? this.civitaiServerTag() : this.tagFilter().join(','),
  }));

  selectedModel = signal<CivitaiModel | null>(null);
  selectedHfModel = signal<HfModel | null>(null);
  galleryIndex = signal<number>(0);
  versions = signal<CivitaiVersion[]>([]);
  hfFiles = signal<{ filename: string; size: number; url: string }[]>([]);
  selectedHfRepoId = signal('');
  hfDescription = signal('');
  hfDescriptionLoading = signal(false);

  searching = signal(false);
  searchError = signal('');
  loadingVersions = signal(false);
  loadingMore = signal(false);
  versionsError = signal('');

  // Pagination state
  civitaiCursor = signal('');
  civitaiHasMore = signal(false);
  hfPage = signal(0);
  hfHasMore = signal(false);
  loadMoreError = signal('');

  activeHasMore = computed(() =>
    this.platform() === 'civitai' ? this.civitaiHasMore() : this.hfHasMore(),
  );

  // Batch selection: key = `${versionId}_${fileId}` → {file, versionId}
  selectedCivitaiFiles = signal(new Map<string, { file: CivitaiFile; versionId: number }>());

  selectedCivitaiCount = computed(() => this.selectedCivitaiFiles().size);

  constructor() {
    toObservable(this.filterParams)
      .pipe(skip(1), debounceTime(300), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        if (this.hasSearched()) this.search();
      });
  }

  fileStatus(filename: string) {
    return this.installed.fileStatus(filename);
  }

  search() {
    this.hasSearched.set(true);
    this.searching.set(true);
    this.civitaiResults.set([]);
    this.hfResults.set([]);
    this.civitaiCursor.set('');
    this.civitaiHasMore.set(false);
    this.hfPage.set(0);
    this.hfHasMore.set(false);
    this.loadMoreError.set('');
    this.searchError.set('');
    this.selectedCivitaiFiles.set(new Map());

    if (this.platform() === 'civitai') {
      this.civitaiService
        .search({
          q: this.query(),
          type: this.modelType(),
          page: 1,
          cursor: '',
          baseModel: this.civitaiBaseModel(),
          sort: this.civitaiSort(),
          period: this.civitaiPeriod(),
          tags: this.tagFilter(),
        })
        .subscribe({
          next: (r) => {
            this.civitaiResults.set(r.items);
            this.civitaiCursor.set(r.metadata?.nextCursor ?? '');
            this.civitaiHasMore.set(!!r.metadata?.nextCursor);
            this.searching.set(false);
            if (r.items.length > 0) this.selectCivitai(r.items[0]);
          },
          error: (err: HttpErrorResponse) => {
            this.searchError.set(err.error?.error ?? err.message ?? 'Search failed');
            this.searching.set(false);
          },
        });
    } else {
      this.hfService
        .search(
          this.query(),
          this.modelType(),
          0,
          this.hfSort(),
          -1,
          this.formatFilter(),
          this.tagFilter(),
        )
        .subscribe({
          next: (r) => {
            this.hfResults.set(r.items);
            this.hfPage.set(r.nextPage);
            this.hfHasMore.set(r.hasMore);
            this.searching.set(false);
            if (r.items.length > 0) this.selectHf(r.items[0]);
          },
          error: (err: HttpErrorResponse) => {
            this.searchError.set(err.error?.error ?? err.message ?? 'Search failed');
            this.searching.set(false);
          },
        });
    }
  }

  loadMore() {
    const wasError = !!this.loadMoreError();
    this.loadMoreError.set('');
    this.loadingMore.set(true);
    if (this.platform() === 'civitai') {
      this.civitaiService
        .search({
          q: this.query(),
          type: this.modelType(),
          page: 1,
          cursor: this.civitaiCursor(),
          baseModel: this.civitaiBaseModel(),
          sort: this.civitaiSort(),
          period: this.civitaiPeriod(),
          tags: this.tagFilter(),
        })
        .subscribe({
          next: (r) => {
            if (r.items.length === 0 && !wasError) {
              const msg = this.translate.instant('download_search.error.no_results');
              this.loadMoreError.set(msg);
              this.notifService.show('error', msg);
            } else {
              this.civitaiResults.update((prev) => [...prev, ...r.items]);
              this.civitaiCursor.set(r.metadata?.nextCursor ?? '');
              this.civitaiHasMore.set(!!r.metadata?.nextCursor);
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
    } else {
      this.hfService
        .search(
          this.query(),
          this.modelType(),
          this.hfPage(),
          this.hfSort(),
          -1,
          this.formatFilter(),
          this.tagFilter(),
        )
        .subscribe({
          next: (r) => {
            if (r.items.length === 0 && !wasError) {
              const msg = this.translate.instant('download_search.error.no_results');
              this.loadMoreError.set(msg);
              this.notifService.show('error', msg);
            } else {
              this.hfResults.update((prev) => [...prev, ...r.items]);
              this.hfPage.set(r.nextPage);
              this.hfHasMore.set(r.hasMore);
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

  selectCivitai(model: CivitaiModel) {
    const targetId = model.id;
    this.selectedModel.set(model);
    this.galleryIndex.set(0);
    this.versions.set([]);
    this.versionsError.set('');
    this.loadingVersions.set(true);
    this.selectedCivitaiFiles.set(new Map());
    this.civitaiFileTypes.set({});
    this.civitaiFileBaseModels.set({});
    this.civitaiService.getVersions(model.id).subscribe({
      next: (v) => {
        if (this.selectedModel()?.id !== targetId) return;
        this.versions.set(v.versions);
        const detected = (v.model_type as ModelType) ?? 'checkpoints';
        const types: Record<string, ModelType> = {};
        const baseModels: Record<string, string> = {};
        for (const ver of v.versions) {
          for (const f of ver.files) {
            const key = `${ver.id}_${f.id}`;
            types[key] = detected;
            const det = this.installed.detect(f.name);
            baseModels[key] = ver.baseModel || det.baseModel;
          }
        }
        this.civitaiFileTypes.set(types);
        this.civitaiFileBaseModels.set(baseModels);
        const selection = new Map<string, { file: CivitaiFile; versionId: number }>();
        for (const ver of v.versions) {
          for (const f of ver.files) {
            if (f.primary) {
              selection.set(`${ver.id}_${f.id}`, { file: f, versionId: ver.id });
            }
          }
        }
        this.selectedCivitaiFiles.set(selection);
        this.loadingVersions.set(false);
      },
      error: (err) => {
        if (this.selectedModel()?.id !== targetId) return;
        this.versionsError.set(
          err?.error?.error ?? this.translate.instant('download_search.error.load_versions_failed'),
        );
        this.loadingVersions.set(false);
      },
    });
  }

  toggleCivitaiFile(versionId: number, file: CivitaiFile) {
    const key = `${versionId}_${file.id}`;
    this.selectedCivitaiFiles.update((prev) => {
      const next = new Map(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.set(key, { file, versionId });
      }
      return next;
    });
  }

  isCivitaiFileSelected(versionId: number, file: CivitaiFile): boolean {
    return this.selectedCivitaiFiles().has(`${versionId}_${file.id}`);
  }

  downloadFile(file: CivitaiFile, versionId: number) {
    this.installed.enqueue(
      file.downloadUrl,
      this.civitaiFileType(versionId, file),
      file.name,
      'civitai',
      String(versionId),
      this.civitaiFileBaseModel(versionId, file),
    );
  }

  downloadSelectedCivitai() {
    for (const { file, versionId } of this.selectedCivitaiFiles().values()) {
      this.installed.enqueue(
        file.downloadUrl,
        this.civitaiFileType(versionId, file),
        file.name,
        'civitai',
        String(versionId),
        this.civitaiFileBaseModel(versionId, file),
      );
    }
    this.selectedCivitaiFiles.set(new Map());
  }

  selectHf(model: HfModel) {
    const repoId = model.modelId ?? model.id;
    this.selectedHfModel.set(model);
    this.selectedHfRepoId.set(repoId);
    this.galleryIndex.set(0);
    this.hfFiles.set([]);
    this.hfRowTypes.set({});
    this.hfRowBaseModels.set({});
    this.hfDescription.set('');
    this.hfService.getFiles(repoId).subscribe({
      next: (files) => {
        if (this.selectedHfRepoId() !== repoId) return;
        this.hfFiles.set(files);
        const types: Record<string, ModelType> = {};
        const baseModels: Record<string, string> = {};
        for (const f of files) {
          const det = this.installed.detect(f.filename);
          if (det.modelType) types[f.filename] = det.modelType;
          if (det.baseModel) baseModels[f.filename] = det.baseModel;
        }
        this.hfRowTypes.set(types);
        this.hfRowBaseModels.set(baseModels);
      },
    });
    if (model.description) {
      this.hfDescription.set(model.description);
    } else {
      this.hfDescriptionLoading.set(true);
      this.hfService.getReadme(repoId).subscribe({
        next: (desc) => {
          if (this.selectedHfRepoId() !== repoId) return;
          this.hfDescription.set(desc);
          this.hfDescriptionLoading.set(false);
        },
        error: () => {
          this.hfDescriptionLoading.set(false);
        },
      });
    }
  }

  downloadHf(file: { filename: string; size: number; url: string }) {
    this.installed.enqueue(
      file.url,
      this.hfRowType(file.filename),
      file.filename,
      'huggingface',
      this.selectedHfRepoId(),
      this.hfRowBaseModel(file.filename),
    );
  }

  formatSize = formatSize;

  civitaiThumb(model: CivitaiModel): string {
    return model.modelVersions?.[0]?.images?.[0]?.url ?? '';
  }

  civitaiGalleryImages(model: CivitaiModel): string[] {
    return (model.modelVersions?.[0]?.images ?? [])
      .slice(0, 8)
      .map((i) => i.url)
      .filter(Boolean);
  }

  isVideo = isVideo;

  setGalleryIndex(i: number) {
    this.galleryIndex.set(i);
  }

  currentGalleryUrl(model: CivitaiModel): string {
    const images = this.civitaiGalleryImages(model);
    return images[this.galleryIndex()] ?? '';
  }

  civitaiModelBaseModel(model: CivitaiModel): string {
    return model.modelVersions?.[0]?.baseModel ?? '';
  }

  hfGalleryImages(model: HfModel): string[] {
    return model.images ?? [];
  }

  currentHfGalleryUrl(model: HfModel): string {
    return this.hfGalleryImages(model)[this.galleryIndex()] ?? '';
  }

  civitaiTriggerWords(model: CivitaiModel): string[] {
    return model.modelVersions?.[0]?.trainedWords ?? [];
  }

  civitaiSourceUrl(model: CivitaiModel): string {
    return `https://civitai.com/models/${model.id}`;
  }

  hfSourceUrl(model: HfModel): string {
    return `https://huggingface.co/${model.modelId ?? model.id}`;
  }

  onImgError(event: Event) {
    (event.target as HTMLImageElement).style.display = 'none';
  }
}
