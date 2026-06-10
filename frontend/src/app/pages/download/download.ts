import { Component, signal, inject, computed, DestroyRef, WritableSignal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { toSignal, toObservable, takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { skip, debounceTime } from 'rxjs';
import { DownloadService, DownloadTask } from '../../services/download';
import { CivitaiService, CivitaiModel, CivitaiVersion, CivitaiFile } from '../../services/civitai';
import { HuggingFaceService, HfModel } from '../../services/huggingface';
import { ModelService } from '../../services/model';
import { NotificationService } from '../../services/notification';
import { KeywordsService } from '../../services/keywords';
import { ModelType } from '../../utils/model-types';
import { detectFromFilename, FilenameKeyword } from '../../utils/filename-detector';
import { formatSize } from '../../utils/format';
import { isVideo } from '../../utils/media';
import { ModelTypeSelect } from '../../components/model-type-select/model-type-select';
import { BaseModelSelect } from '../../components/base-model-select/base-model-select';
import { SafeHtmlPipe } from '../../utils/safe-html.pipe';
import { DownloadHistory } from './download-history';
import { DownloadQueue } from './download-queue';
import { PasteLink } from './paste-link';

type Platform = 'civitai' | 'huggingface';

@Component({
  selector: 'app-download',
  imports: [
    CommonModule,
    FormsModule,
    ModelTypeSelect,
    BaseModelSelect,
    SafeHtmlPipe,
    DownloadHistory,
    DownloadQueue,
    PasteLink,
  ],
  templateUrl: './download.html',
  styleUrl: './download.scss',
})
export class Download {
  private readonly dlService = inject(DownloadService);
  private readonly civitaiService = inject(CivitaiService);
  private readonly hfService = inject(HuggingFaceService);
  private readonly modelService = inject(ModelService);
  private readonly notifService = inject(NotificationService);
  private readonly keywordsService = inject(KeywordsService);
  private readonly destroyRef = inject(DestroyRef);

  readonly keywords = toSignal(this.keywordsService.getKeywords(), {
    initialValue: [] as FilenameKeyword[],
  });

  readonly civitaiSortOptions = [
    { label: 'Most Downloaded', value: 'Most Downloaded' },
    { label: 'Highest Rated', value: 'Highest Rated' },
    { label: 'Newest', value: 'Newest' },
  ];
  readonly civitaiPeriodOptions = [
    { label: 'All Time', value: 'AllTime' },
    { label: 'Year', value: 'Year' },
    { label: 'Month', value: 'Month' },
    { label: 'Week', value: 'Week' },
    { label: 'Day', value: 'Day' },
  ];
  readonly hfSortOptions = [
    { label: 'Downloads', value: 'downloads' },
    { label: 'Likes', value: 'likes' },
    { label: 'Trending', value: 'trending' },
    { label: 'Recently Updated', value: 'lastModified' },
    { label: 'Recently Created', value: 'createdAt' },
  ];
  readonly formatOptions = [
    { label: 'All formats', value: '' },
    { label: '.safetensors', value: '.safetensors' },
    { label: '.gguf', value: '.gguf' },
    { label: '.ckpt', value: '.ckpt' },
    { label: '.pt', value: '.pt' },
    { label: '.bin', value: '.bin' },
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

  // All per-row "type"/"base-model" overrides are keyed maps with a default; these two
  // helpers carry the read/update logic so each accessor below stays a one-line binding.
  private readOverride<T>(map: WritableSignal<Record<string, T>>, key: string, fallback: T): T {
    return map()[key] ?? fallback;
  }
  private writeOverride<T>(map: WritableSignal<Record<string, T>>, key: string, value: T): void {
    map.update((m) => ({ ...m, [key]: value }));
  }

  private fileKey(versionId: number, file: CivitaiFile): string {
    return `${versionId}_${file.id}`;
  }

  hfRowType(name: string): ModelType {
    return this.readOverride(this.hfRowTypes, name, 'checkpoints');
  }
  setHfRowType(name: string, t: ModelType) {
    this.writeOverride(this.hfRowTypes, name, t);
  }

  civitaiFileType(versionId: number, file: CivitaiFile): ModelType {
    return this.readOverride(this.civitaiFileTypes, this.fileKey(versionId, file), 'checkpoints');
  }
  setCivitaiFileType(versionId: number, file: CivitaiFile, t: ModelType) {
    this.writeOverride(this.civitaiFileTypes, this.fileKey(versionId, file), t);
  }

  hfRowBaseModel(name: string): string {
    return this.readOverride(this.hfRowBaseModels, name, '');
  }
  setHfRowBaseModel(name: string, v: string) {
    this.writeOverride(this.hfRowBaseModels, name, v);
  }

  civitaiFileBaseModel(versionId: number, file: CivitaiFile): string {
    return this.readOverride(this.civitaiFileBaseModels, this.fileKey(versionId, file), '');
  }
  setCivitaiFileBaseModel(versionId: number, file: CivitaiFile, v: string) {
    this.writeOverride(this.civitaiFileBaseModels, this.fileKey(versionId, file), v);
  }

  private detect(filename: string) {
    return detectFromFilename(filename, this.keywords());
  }

  civitaiSort = signal('');
  civitaiPeriod = signal('AllTime');
  civitaiBaseModel = signal('');
  hfSort = signal('downloads');
  formatFilter = signal('');
  tagFilter = signal<string[]>([]);
  tagInput = signal('');
  hasSearched = signal(false);

  installedFilenames = signal(new Set<string>());

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

  activeTab = signal<'active' | 'history'>('active');

  // Live download tasks — used here only to flag search results as already installed.
  // The Active-downloads queue UI lives in the DownloadQueue child component.
  readonly activeTasks = toSignal(this.dlService.activeTasks$, {
    initialValue: [] as DownloadTask[],
  });

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
    this.modelService
      .listModels()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((models) => {
        const names = new Set<string>();
        for (const files of Object.values(models)) {
          for (const f of files) names.add(f.filename);
        }
        this.installedFilenames.set(names);
      });

    toObservable(this.activeTasks)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((tasks) => {
        const done = tasks.filter((t) => t.status === 'done').map((t) => t.filename);
        if (done.length > 0) {
          this.installedFilenames.update((prev) => {
            const next = new Set(prev);
            done.forEach((f) => next.add(f));
            return next;
          });
        }
      });

    toObservable(this.filterParams)
      .pipe(skip(1), debounceTime(300), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        if (this.hasSearched()) this.search();
      });
  }

  fileStatus(filename: string): 'idle' | 'downloading' | 'installed' | 'error' {
    // HuggingFace files may have a subfolder prefix in their listed name (e.g.
    // "split_files/model.safetensors"). The downloader strips this to the basename
    // before saving, so we match on the basename here for correct status resolution.
    const base = filename.split('/').pop() ?? filename;
    const task = this.activeTasks().find((t) => t.filename === base);
    if (task) {
      if (task.status === 'done') return 'installed';
      if (task.status === 'error') return 'error';
      return 'downloading';
    }
    return this.installedFilenames().has(base) ? 'installed' : 'idle';
  }

  /** Start a download and toast on success. Shared by all download buttons. */
  private enqueue(
    url: string,
    type: ModelType,
    filename: string,
    platform: string,
    sourceId: string,
    baseModel = '',
  ) {
    this.dlService.startDownload(url, type, filename, platform, sourceId, baseModel).subscribe({
      next: () => this.notifService.show('success', `Download enqueued: ${filename}`),
    });
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
              const msg = 'No results returned';
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
            const msg = err.error?.error ?? err.message ?? 'Request failed';
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
              const msg = 'No results returned';
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
            const msg = err.error?.error ?? err.message ?? 'Request failed';
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
    this.tagInput.set('');
  }

  addTagFromInput() {
    const raw = this.tagInput().trim();
    if (raw) this.addTag(raw);
  }

  removeTag(tag: string) {
    this.tagFilter.update((tags) => tags.filter((t) => t !== tag));
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
            const det = this.detect(f.name);
            baseModels[key] = ver.baseModel || det.baseModel;
          }
        }
        this.civitaiFileTypes.set(types);
        this.civitaiFileBaseModels.set(baseModels);
        this.loadingVersions.set(false);
      },
      error: (err) => {
        if (this.selectedModel()?.id !== targetId) return;
        this.versionsError.set(err?.error?.error ?? 'Failed to load versions');
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
    this.enqueue(
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
      this.enqueue(
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
          const det = this.detect(f.filename);
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
    this.enqueue(
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
