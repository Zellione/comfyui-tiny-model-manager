import { Component, signal, inject, computed, DestroyRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { toSignal, toObservable, takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, skip } from 'rxjs';
import { debounceTime, distinctUntilChanged, switchMap, of, catchError, map } from 'rxjs';
import { DownloadService, DownloadTask } from '../../services/download';
import {
  CivitaiService,
  CivitaiModel,
  CivitaiVersion,
  CivitaiFile,
  CivitaiDirectLinkInfo,
} from '../../services/civitai';
import { HuggingFaceService, HfModel } from '../../services/huggingface';
import { ModelService } from '../../services/model';
import { NotificationService } from '../../services/notification';
import { detectLink, LinkKind } from '../../utils/link-detector';

type HfFileItem = { filename: string; size: number; url: string };

type Platform = 'civitai' | 'huggingface';
type ModelType =
  | 'checkpoints'
  | 'loras'
  | 'embeddings'
  | 'vae'
  | 'controlnet'
  | 'upscale_models'
  | 'hypernetworks'
  | 'clip_vision'
  | 'style_models'
  | 'gligen'
  | 'diffusion_models'
  | 'text_encoders'
  | 'photomaker'
  | 'vae_approx'
  | 'unet'
  | 'clip';

@Component({
  selector: 'app-download',
  imports: [CommonModule, FormsModule],
  templateUrl: './download.html',
  styleUrl: './download.scss',
})
export class Download {
  private dlService = inject(DownloadService);
  private civitaiService = inject(CivitaiService);
  private hfService = inject(HuggingFaceService);
  private modelService = inject(ModelService);
  private notifService = inject(NotificationService);
  private destroyRef = inject(DestroyRef);
  private pasteUrl$ = new Subject<string>();

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
  modelTypes: ModelType[] = [
    'checkpoints',
    'loras',
    'embeddings',
    'vae',
    'controlnet',
    'upscale_models',
    'hypernetworks',
    'clip_vision',
    'style_models',
    'gligen',
    'diffusion_models',
    'text_encoders',
    'photomaker',
    'vae_approx',
    'unet',
    'clip',
  ];

  hfRowTypes = signal<Record<string, ModelType>>({});
  linkHfRowTypes = signal<Record<string, ModelType>>({});
  civitaiFileTypes = signal<Record<string, ModelType>>({});
  linkCivitaiFileTypes = signal<Record<string, ModelType>>({});

  hfRowType(name: string): ModelType {
    return this.hfRowTypes()[name] ?? 'checkpoints';
  }
  setHfRowType(name: string, t: ModelType) {
    this.hfRowTypes.update((m) => ({ ...m, [name]: t }));
  }

  linkHfRowType(name: string): ModelType {
    return this.linkHfRowTypes()[name] ?? 'checkpoints';
  }
  setLinkHfRowType(name: string, t: ModelType) {
    this.linkHfRowTypes.update((m) => ({ ...m, [name]: t }));
  }

  civitaiFileType(versionId: number, file: CivitaiFile): ModelType {
    return this.civitaiFileTypes()[`${versionId}_${file.id}`] ?? 'checkpoints';
  }
  setCivitaiFileType(versionId: number, file: CivitaiFile, t: ModelType) {
    this.civitaiFileTypes.update((m) => ({ ...m, [`${versionId}_${file.id}`]: t }));
  }

  linkCivitaiFileType(versionId: number, file: CivitaiFile): ModelType {
    return this.linkCivitaiFileTypes()[`${versionId}_${file.id}`] ?? 'checkpoints';
  }
  setLinkCivitaiFileType(versionId: number, file: CivitaiFile, t: ModelType) {
    this.linkCivitaiFileTypes.update((m) => ({ ...m, [`${versionId}_${file.id}`]: t }));
  }

  civitaiSort = signal('');
  civitaiPeriod = signal('AllTime');
  civitaiBaseModel = signal('');
  hfSort = signal('downloads');
  formatFilter = signal('');
  tagFilter = signal<string[]>([]);
  tagInput = signal('');
  hasSearched = signal(false);

  // Paste-a-link section
  pasteUrl = signal('');
  linkKind = signal<LinkKind>({ type: 'empty' });
  linkModelType = signal<ModelType>('checkpoints');
  linkResolving = signal(false);
  linkError = signal('');
  linkResolved = signal<CivitaiDirectLinkInfo | null>(null);
  linkImages = signal<string[]>([]);

  // F-19: HF repo link state
  linkHfFiles = signal<HfFileItem[]>([]);

  // F-20: CivitAI model link state
  linkVersions = signal<CivitaiVersion[]>([]);
  linkVersionsError = signal('');
  linkCivitaiSelected = signal(new Map<string, { file: CivitaiFile; versionId: number }>());
  linkCivitaiSelectedCount = computed(() => this.linkCivitaiSelected().size);

  installedFilenames = signal(new Set<string>());

  hfResolveKind = computed(() => {
    const k = this.linkKind();
    return k.type === 'hf-resolve' ? k : null;
  });
  civitaiDownloadKind = computed(() => {
    const k = this.linkKind();
    return k.type === 'civitai-download' ? k : null;
  });
  hfRepoKind = computed(() => {
    const k = this.linkKind();
    return k.type === 'hf-repo' ? k : null;
  });
  civitaiModelKind = computed(() => {
    const k = this.linkKind();
    return k.type === 'civitai-model' ? k : null;
  });
  linkFilename = computed(() => {
    const k = this.linkKind();
    if (k.type === 'hf-resolve') return k.filename;
    if (k.type === 'civitai-download') return this.linkResolved()?.filename ?? '';
    return '';
  });
  canSubmitLink = computed(() => {
    const k = this.linkKind();
    if (k.type === 'hf-resolve') return true;
    if (k.type === 'civitai-download') return !!this.linkResolved() && !this.linkResolving();
    return false;
  });

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
  private civitaiServerTag = computed(() => this.tagFilter()[0] ?? '');

  private filterParams = computed(() => ({
    civitaiSort: this.civitaiSort(),
    civitaiPeriod: this.civitaiPeriod(),
    civitaiBaseModel: this.civitaiBaseModel(),
    hfSort: this.hfSort(),
    formatFilter: this.formatFilter(),
    // civitaiServerTag() not tagFilter() — avoids re-fetch when only client-side extra tags change.
    serverTag: this.platform() === 'civitai' ? this.civitaiServerTag() : this.tagFilter().join(','),
  }));

  activeTasks = toSignal(this.dlService.activeTasks$, { initialValue: [] as DownloadTask[] });

  selectedModel = signal<CivitaiModel | null>(null);
  selectedHfModel = signal<HfModel | null>(null);
  galleryIndex = signal<number>(0);
  versions = signal<CivitaiVersion[]>([]);
  hfFiles = signal<{ filename: string; size: number; url: string }[]>([]);
  selectedHfRepoId = signal('');
  hfDescription = signal('');
  hfDescriptionLoading = signal(false);

  searching = signal(false);
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
    this.pasteUrl$
      .pipe(
        debounceTime(300),
        distinctUntilChanged(),
        switchMap((url) => {
          const kind = detectLink(url);
          this.linkKind.set(kind);
          this.linkResolved.set(null);
          this.linkImages.set([]);
          this.linkError.set('');
          this.linkHfFiles.set([]);
          this.linkVersions.set([]);
          this.linkVersionsError.set('');
          this.linkCivitaiSelected.set(new Map());
          this.linkCivitaiFileTypes.set({});
          if (kind.type === 'hf-resolve') {
            this.linkResolving.set(true);
            return this.hfService.resolveDirectLink(kind.repo).pipe(
              map((r) => ({ tag: 'hf-resolve' as const, image_urls: r.image_urls })),
              catchError(() => of({ tag: 'hf-resolve' as const, image_urls: [] as string[] })),
            );
          }
          if (kind.type === 'civitai-download') {
            this.linkResolving.set(true);
            return this.civitaiService.resolveDirectLink(kind.versionId).pipe(
              map((r) => ({ tag: 'civitai-download' as const, ...r })),
              catchError((err) => {
                this.linkError.set(err?.error?.error ?? 'Failed to resolve link');
                this.linkResolving.set(false);
                return of(null);
              }),
            );
          }
          if (kind.type === 'hf-repo') {
            this.linkResolving.set(true);
            return this.hfService.getFiles(kind.repo).pipe(
              map((files) => ({ tag: 'hf-repo' as const, files })),
              catchError(() => {
                this.linkError.set('Failed to load files from repository');
                this.linkResolving.set(false);
                return of(null);
              }),
            );
          }
          if (kind.type === 'civitai-model') {
            this.linkResolving.set(true);
            return this.civitaiService.getVersions(kind.modelId).pipe(
              map((r) => ({
                tag: 'civitai-model' as const,
                versions: r.versions,
                model_type: r.model_type,
              })),
              catchError((err) => {
                this.linkVersionsError.set(err?.error?.error ?? 'Failed to load model versions');
                this.linkResolving.set(false);
                return of(null);
              }),
            );
          }
          return of(null);
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((result) => {
        if (result) {
          if (result.tag === 'hf-resolve') {
            this.linkImages.set(result.image_urls ?? []);
          } else if (result.tag === 'civitai-download') {
            this.linkResolved.set(result);
            this.linkModelType.set((result.model_type as ModelType) ?? 'checkpoints');
            this.linkImages.set(result.image_urls ?? []);
          } else if (result.tag === 'hf-repo') {
            this.linkHfFiles.set(result.files);
          } else if (result.tag === 'civitai-model') {
            this.linkVersions.set(result.versions);
            this.linkModelType.set((result.model_type as ModelType) ?? 'checkpoints');
            const detected = (result.model_type as ModelType) ?? 'checkpoints';
            const types: Record<string, ModelType> = {};
            for (const v of result.versions) {
              for (const f of v.files) {
                types[`${v.id}_${f.id}`] = detected;
              }
            }
            this.linkCivitaiFileTypes.set(types);
          }
        }
        this.linkResolving.set(false);
      });

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

  onPasteUrlChange(url: string) {
    this.pasteUrl.set(url);
    this.pasteUrl$.next(url);
  }

  submitDirectLink() {
    const kind = this.linkKind();
    const type = this.linkModelType();
    if (kind.type === 'hf-resolve') {
      this.dlService
        .startDownload(this.pasteUrl(), type, kind.filename, 'huggingface', kind.repo)
        .subscribe({
          next: () => this.notifService.show('success', `Download enqueued: ${kind.filename}`),
        });
    } else if (kind.type === 'civitai-download') {
      const r = this.linkResolved();
      if (!r) return;
      this.dlService
        .startDownload(this.pasteUrl(), type, r.filename, 'civitai', String(kind.versionId))
        .subscribe({
          next: () => this.notifService.show('success', `Download enqueued: ${r.filename}`),
        });
    }
    this.pasteUrl.set('');
    this.linkKind.set({ type: 'empty' });
    this.linkResolved.set(null);
    this.linkImages.set([]);
    this.linkError.set('');
  }

  // F-19 — HF repo link method
  downloadLinkHfFile(f: HfFileItem) {
    const kind = this.linkKind();
    const repo = kind.type === 'hf-repo' ? kind.repo : '';
    this.dlService
      .startDownload(f.url, this.linkHfRowType(f.filename), f.filename, 'huggingface', repo)
      .subscribe({
        next: () => this.notifService.show('success', `Download enqueued: ${f.filename}`),
      });
  }

  // F-20 — CivitAI model link methods
  toggleLinkCivitaiFile(versionId: number, file: CivitaiFile) {
    const key = `${versionId}_${file.id}`;
    this.linkCivitaiSelected.update((prev) => {
      const next = new Map(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.set(key, { file, versionId });
      }
      return next;
    });
  }

  isLinkCivitaiFileSelected(versionId: number, file: CivitaiFile): boolean {
    return this.linkCivitaiSelected().has(`${versionId}_${file.id}`);
  }

  downloadLinkFile(file: CivitaiFile, versionId: number) {
    this.dlService
      .startDownload(
        file.downloadUrl,
        this.linkCivitaiFileType(versionId, file),
        file.name,
        'civitai',
        String(versionId),
      )
      .subscribe({
        next: () => this.notifService.show('success', `Download enqueued: ${file.name}`),
      });
  }

  downloadSelectedLinkCivitai() {
    for (const { file, versionId } of this.linkCivitaiSelected().values()) {
      this.dlService
        .startDownload(
          file.downloadUrl,
          this.linkCivitaiFileType(versionId, file),
          file.name,
          'civitai',
          String(versionId),
        )
        .subscribe({
          next: () => this.notifService.show('success', `Download enqueued: ${file.name}`),
        });
    }
    this.linkCivitaiSelected.set(new Map());
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
    this.selectedCivitaiFiles.set(new Map());

    if (this.platform() === 'civitai') {
      this.civitaiService
        .search(
          this.query(),
          this.modelType(),
          1,
          '',
          this.civitaiBaseModel(),
          this.civitaiSort(),
          this.civitaiPeriod(),
          this.tagFilter(),
        )
        .subscribe({
          next: (r) => {
            this.civitaiResults.set(r.items);
            this.civitaiCursor.set(r.metadata?.nextCursor ?? '');
            this.civitaiHasMore.set(!!r.metadata?.nextCursor);
            this.searching.set(false);
            if (r.items.length > 0) this.selectCivitai(r.items[0]);
          },
          error: () => {
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
          error: () => {
            this.searching.set(false);
          },
        });
    }
  }

  loadMore() {
    this.loadingMore.set(true);
    this.loadMoreError.set('');
    if (this.platform() === 'civitai') {
      this.civitaiService
        .search(
          this.query(),
          this.modelType(),
          1,
          this.civitaiCursor(),
          this.civitaiBaseModel(),
          this.civitaiSort(),
          this.civitaiPeriod(),
          this.tagFilter(),
        )
        .subscribe({
          next: (r) => {
            if (r.items.length === 0) {
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
            if (r.items.length === 0) {
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
    this.civitaiService.getVersions(model.id).subscribe({
      next: (v) => {
        if (this.selectedModel()?.id !== targetId) return;
        this.versions.set(v.versions);
        const detected = (v.model_type as ModelType) ?? 'checkpoints';
        const types: Record<string, ModelType> = {};
        for (const ver of v.versions) {
          for (const f of ver.files) {
            types[`${ver.id}_${f.id}`] = detected;
          }
        }
        this.civitaiFileTypes.set(types);
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
    this.dlService
      .startDownload(
        file.downloadUrl,
        this.civitaiFileType(versionId, file),
        file.name,
        'civitai',
        String(versionId),
      )
      .subscribe({
        next: () => this.notifService.show('success', `Download enqueued: ${file.name}`),
      });
  }

  downloadSelectedCivitai() {
    for (const { file, versionId } of this.selectedCivitaiFiles().values()) {
      this.dlService
        .startDownload(
          file.downloadUrl,
          this.civitaiFileType(versionId, file),
          file.name,
          'civitai',
          String(versionId),
        )
        .subscribe({
          next: () => this.notifService.show('success', `Download enqueued: ${file.name}`),
        });
    }
    this.selectedCivitaiFiles.set(new Map());
  }

  selectHf(model: HfModel) {
    const repoId = model.modelId ?? model.id;
    this.selectedHfModel.set(model);
    this.selectedHfRepoId.set(repoId);
    this.hfFiles.set([]);
    this.hfDescription.set('');
    this.hfService.getFiles(repoId).subscribe({
      next: (files) => {
        if (this.selectedHfRepoId() !== repoId) return;
        this.hfFiles.set(files);
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
    this.dlService
      .startDownload(
        file.url,
        this.hfRowType(file.filename),
        file.filename,
        'huggingface',
        this.selectedHfRepoId(),
      )
      .subscribe({
        next: () => this.notifService.show('success', `Download enqueued: ${file.filename}`),
      });
  }

  formatSize(bytes: number): string {
    if (bytes >= 1e9) return (bytes / 1e9).toFixed(1) + ' GB';
    if (bytes >= 1e6) return (bytes / 1e6).toFixed(1) + ' MB';
    return (bytes / 1e3).toFixed(0) + ' KB';
  }

  activePct(t: DownloadTask): string {
    return t.progress.toFixed(0) + '%';
  }

  civitaiThumb(model: CivitaiModel): string {
    return model.modelVersions?.[0]?.images?.[0]?.url ?? '';
  }

  civitaiGalleryImages(model: CivitaiModel): string[] {
    return (model.modelVersions?.[0]?.images ?? [])
      .slice(0, 8)
      .map((i) => i.url)
      .filter(Boolean);
  }

  isVideo(url: string): boolean {
    const lower = url.toLowerCase();
    return lower.includes('.mp4') || lower.includes('.webm') || lower.includes('.mov');
  }

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
