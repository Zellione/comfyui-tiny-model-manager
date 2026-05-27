import { Component, signal, inject, computed, DestroyRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { toSignal, toObservable, takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, skip } from 'rxjs';
import { debounceTime, distinctUntilChanged, switchMap, of, catchError, map } from 'rxjs';
import { DownloadService, DownloadTask } from '../../services/download';
import { CivitaiService, CivitaiModel, CivitaiVersion, CivitaiFile, CivitaiDirectLinkInfo } from '../../services/civitai';
import { HuggingFaceService, HfModel } from '../../services/huggingface';
import { ModelService } from '../../services/model';
import { detectLink, LinkKind } from '../../utils/link-detector';

type HfFileItem = { filename: string; size: number; url: string };

type Platform = 'civitai' | 'huggingface';
type ModelType = 'checkpoints' | 'loras' | 'embeddings' | 'vae' | 'controlnet';

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
  private destroyRef = inject(DestroyRef);
  private pasteUrl$ = new Subject<string>();

  readonly civitaiSortOptions = [
    { label: 'Most Downloaded', value: 'Most Downloaded' },
    { label: 'Highest Rated',   value: 'Highest Rated' },
    { label: 'Newest',          value: 'Newest' },
  ];
  readonly civitaiPeriodOptions = [
    { label: 'All Time', value: 'AllTime' },
    { label: 'Year',     value: 'Year' },
    { label: 'Month',    value: 'Month' },
    { label: 'Week',     value: 'Week' },
    { label: 'Day',      value: 'Day' },
  ];
  readonly hfSortOptions = [
    { label: 'Downloads',        value: 'downloads' },
    { label: 'Likes',            value: 'likes' },
    { label: 'Trending',         value: 'trending' },
    { label: 'Recently Updated', value: 'lastModified' },
    { label: 'Recently Created', value: 'createdAt' },
  ];
  readonly formatOptions = [
    { label: 'All formats',  value: '' },
    { label: '.safetensors', value: '.safetensors' },
    { label: '.gguf',        value: '.gguf' },
    { label: '.ckpt',        value: '.ckpt' },
    { label: '.pt',          value: '.pt' },
    { label: '.bin',         value: '.bin' },
  ];
  readonly civitaiBaseModelOptions = [
    'SD 1.5', 'SD 2.1', 'SDXL 1.0', 'Pony', 'Illustrious',
    'Flux.1 D', 'Flux.1 S', 'Stable Cascade', 'SDXL Turbo', 'Chroma', 'Qwen',
  ];

  platform = signal<Platform>('civitai');
  query = signal('');
  modelType = signal<ModelType>('checkpoints');
  modelTypes: ModelType[] = ['checkpoints', 'loras', 'embeddings', 'vae', 'controlnet'];

  civitaiSort      = signal('');
  civitaiPeriod    = signal('AllTime');
  civitaiBaseModel = signal('');
  hfSort           = signal('downloads');
  formatFilter     = signal('');
  hasSearched      = signal(false);

  // Paste-a-link section
  pasteUrl      = signal('');
  linkKind      = signal<LinkKind>({ type: 'empty' });
  linkModelType = signal<ModelType>('checkpoints');
  linkResolving = signal(false);
  linkError     = signal('');
  linkResolved  = signal<CivitaiDirectLinkInfo | null>(null);
  linkImages    = signal<string[]>([]);

  // F-19: HF repo link state
  linkHfFiles         = signal<HfFileItem[]>([]);
  linkHfSelected      = signal(new Set<string>());
  linkHfSelectedCount = computed(() => this.linkHfSelected().size);

  // F-20: CivitAI model link state
  linkVersions             = signal<CivitaiVersion[]>([]);
  linkVersionsError        = signal('');
  linkCivitaiSelected      = signal(new Map<string, { file: CivitaiFile; versionId: number }>());
  linkCivitaiSelectedCount = computed(() => this.linkCivitaiSelected().size);

  installedFilenames = signal(new Set<string>());

  hfResolveKind       = computed(() => { const k = this.linkKind(); return k.type === 'hf-resolve' ? k : null; });
  civitaiDownloadKind = computed(() => { const k = this.linkKind(); return k.type === 'civitai-download' ? k : null; });
  hfRepoKind          = computed(() => { const k = this.linkKind(); return k.type === 'hf-repo' ? k : null; });
  civitaiModelKind    = computed(() => { const k = this.linkKind(); return k.type === 'civitai-model' ? k : null; });
  linkFilename        = computed(() => {
    const k = this.linkKind();
    if (k.type === 'hf-resolve') return k.filename;
    if (k.type === 'civitai-download') return this.linkResolved()?.filename ?? '';
    return '';
  });
  canSubmitLink       = computed(() => {
    const k = this.linkKind();
    if (k.type === 'hf-resolve') return true;
    if (k.type === 'civitai-download') return !!this.linkResolved() && !this.linkResolving();
    return false;
  });

  civitaiResults = signal<CivitaiModel[]>([]);
  hfResults = signal<HfModel[]>([]);

  filteredCivitaiResults = computed(() => {
    const fmt = this.formatFilter();
    if (!fmt) return this.civitaiResults();
    return this.civitaiResults().filter(m =>
      m.modelVersions?.some(v => v.files?.some(f => f.name.toLowerCase().endsWith(fmt)))
    );
  });

  filteredHfResults = computed(() => {
    const fmt = this.formatFilter();
    if (!fmt) return this.hfResults();
    return this.hfResults().filter(m => m.formats?.includes(fmt));
  });

  private filterParams = computed(() => ({
    civitaiSort:      this.civitaiSort(),
    civitaiPeriod:    this.civitaiPeriod(),
    civitaiBaseModel: this.civitaiBaseModel(),
    hfSort:           this.hfSort(),
    formatFilter:     this.formatFilter(),
  }));

  activeTasks = toSignal(this.dlService.activeTasks$, { initialValue: [] as DownloadTask[] });

  selectedModel = signal<CivitaiModel | null>(null);
  selectedHfModel = signal<HfModel | null>(null);
  galleryIndex = signal<number>(0);
  versions = signal<CivitaiVersion[]>([]);
  hfFiles = signal<{ filename: string; size: number; url: string }[]>([]);
  selectedHfRepoId = signal('');

  searching = signal(false);
  loadingVersions = signal(false);
  loadingMore = signal(false);
  versionsError = signal('');

  // Pagination state
  civitaiCursor = signal('');
  civitaiHasMore = signal(false);
  hfPage = signal(0);
  hfHasMore = signal(false);

  // Batch selection: key = `${versionId}_${fileId}` → {file, versionId}
  selectedCivitaiFiles = signal(new Map<string, { file: CivitaiFile; versionId: number }>());
  // key = filename
  selectedHfFiles = signal(new Set<string>());

  selectedCivitaiCount = computed(() => this.selectedCivitaiFiles().size);
  selectedHfCount = computed(() => this.selectedHfFiles().size);

  constructor() {
    this.pasteUrl$
      .pipe(
        debounceTime(300),
        distinctUntilChanged(),
        switchMap(url => {
          const kind = detectLink(url);
          this.linkKind.set(kind);
          this.linkResolved.set(null);
          this.linkImages.set([]);
          this.linkError.set('');
          this.linkHfFiles.set([]);
          this.linkHfSelected.set(new Set());
          this.linkVersions.set([]);
          this.linkVersionsError.set('');
          this.linkCivitaiSelected.set(new Map());
          if (kind.type === 'hf-resolve') {
            this.linkResolving.set(true);
            return this.hfService.resolveDirectLink(kind.repo).pipe(
              map(r => ({ tag: 'hf-resolve' as const, image_urls: r.image_urls })),
              catchError(() => of({ tag: 'hf-resolve' as const, image_urls: [] as string[] }))
            );
          }
          if (kind.type === 'civitai-download') {
            this.linkResolving.set(true);
            return this.civitaiService.resolveDirectLink(kind.versionId).pipe(
              map(r => ({ tag: 'civitai-download' as const, ...r })),
              catchError(err => {
                this.linkError.set(err?.error?.error ?? 'Failed to resolve link');
                this.linkResolving.set(false);
                return of(null);
              })
            );
          }
          if (kind.type === 'hf-repo') {
            this.linkResolving.set(true);
            return this.hfService.getFiles(kind.repo).pipe(
              map(files => ({ tag: 'hf-repo' as const, files })),
              catchError(() => {
                this.linkError.set('Failed to load files from repository');
                this.linkResolving.set(false);
                return of(null);
              })
            );
          }
          if (kind.type === 'civitai-model') {
            this.linkResolving.set(true);
            return this.civitaiService.getVersions(kind.modelId).pipe(
              map(r => ({ tag: 'civitai-model' as const, versions: r.versions, model_type: r.model_type })),
              catchError(err => {
                this.linkVersionsError.set(err?.error?.error ?? 'Failed to load model versions');
                this.linkResolving.set(false);
                return of(null);
              })
            );
          }
          return of(null);
        }),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe(result => {
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
          }
        }
        this.linkResolving.set(false);
      });

    this.modelService.listModels().pipe(
      takeUntilDestroyed(this.destroyRef)
    ).subscribe(models => {
      const names = new Set<string>();
      for (const files of Object.values(models)) {
        for (const f of files) names.add(f.filename);
      }
      this.installedFilenames.set(names);
    });

    toObservable(this.activeTasks).pipe(
      takeUntilDestroyed(this.destroyRef)
    ).subscribe(tasks => {
      const done = tasks.filter(t => t.status === 'done').map(t => t.filename);
      if (done.length > 0) {
        this.installedFilenames.update(prev => {
          const next = new Set(prev);
          done.forEach(f => next.add(f));
          return next;
        });
      }
    });

    toObservable(this.filterParams).pipe(
      skip(1),
      debounceTime(300),
      takeUntilDestroyed(this.destroyRef)
    ).subscribe(() => {
      if (this.hasSearched()) this.search();
    });
  }

  fileStatus(filename: string): 'idle' | 'downloading' | 'installed' | 'error' {
    const task = this.activeTasks().find(t => t.filename === filename);
    if (task) {
      if (task.status === 'done') return 'installed';
      if (task.status === 'error') return 'error';
      return 'downloading';
    }
    return this.installedFilenames().has(filename) ? 'installed' : 'idle';
  }

  onPasteUrlChange(url: string) {
    this.pasteUrl.set(url);
    this.pasteUrl$.next(url);
  }

  submitDirectLink() {
    const kind = this.linkKind();
    const type = this.linkModelType();
    if (kind.type === 'hf-resolve') {
      this.dlService.startDownload(this.pasteUrl(), type, kind.filename, 'huggingface', kind.repo).subscribe();
    } else if (kind.type === 'civitai-download') {
      const r = this.linkResolved();
      if (!r) return;
      this.dlService.startDownload(this.pasteUrl(), type, r.filename, 'civitai', String(kind.versionId)).subscribe();
    }
    this.pasteUrl.set('');
    this.linkKind.set({ type: 'empty' });
    this.linkResolved.set(null);
    this.linkImages.set([]);
    this.linkError.set('');
  }

  // F-19 — HF repo link methods
  toggleLinkHfFile(filename: string) {
    this.linkHfSelected.update(prev => {
      const next = new Set(prev);
      if (next.has(filename)) { next.delete(filename); } else { next.add(filename); }
      return next;
    });
  }

  isLinkHfFileSelected(filename: string): boolean {
    return this.linkHfSelected().has(filename);
  }

  downloadLinkHfFile(f: HfFileItem) {
    const kind = this.linkKind();
    const repo = kind.type === 'hf-repo' ? kind.repo : '';
    this.dlService.startDownload(f.url, this.linkModelType(), f.filename, 'huggingface', repo).subscribe();
  }

  downloadSelectedLinkHf() {
    const kind = this.linkKind();
    const repo = kind.type === 'hf-repo' ? kind.repo : '';
    for (const filename of this.linkHfSelected()) {
      const f = this.linkHfFiles().find(x => x.filename === filename);
      if (f) this.dlService.startDownload(f.url, this.linkModelType(), f.filename, 'huggingface', repo).subscribe();
    }
    this.linkHfSelected.set(new Set());
  }

  // F-20 — CivitAI model link methods
  toggleLinkCivitaiFile(versionId: number, file: CivitaiFile) {
    const key = `${versionId}_${file.id}`;
    this.linkCivitaiSelected.update(prev => {
      const next = new Map(prev);
      if (next.has(key)) { next.delete(key); } else { next.set(key, { file, versionId }); }
      return next;
    });
  }

  isLinkCivitaiFileSelected(versionId: number, file: CivitaiFile): boolean {
    return this.linkCivitaiSelected().has(`${versionId}_${file.id}`);
  }

  downloadLinkFile(file: CivitaiFile, versionId: number) {
    this.dlService.startDownload(file.downloadUrl, this.linkModelType(), file.name, 'civitai', String(versionId)).subscribe();
  }

  downloadSelectedLinkCivitai() {
    for (const { file, versionId } of this.linkCivitaiSelected().values()) {
      this.dlService.startDownload(file.downloadUrl, this.linkModelType(), file.name, 'civitai', String(versionId)).subscribe();
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
    this.selectedCivitaiFiles.set(new Map());
    this.selectedHfFiles.set(new Set());

    if (this.platform() === 'civitai') {
      this.civitaiService.search(
        this.query(), this.modelType(), 1, '',
        this.civitaiBaseModel(), this.civitaiSort(), this.civitaiPeriod()
      ).subscribe({
        next: r => {
          this.civitaiResults.set(r.items);
          this.civitaiCursor.set(r.metadata?.nextCursor ?? '');
          this.civitaiHasMore.set(!!r.metadata?.nextCursor);
          this.searching.set(false);
          if (r.items.length > 0) this.selectCivitai(r.items[0]);
        },
        error: () => { this.searching.set(false); },
      });
    } else {
      this.hfService.search(this.query(), this.modelType(), 0, this.hfSort(), -1, this.formatFilter()).subscribe({
        next: r => {
          this.hfResults.set(r.items);
          this.hfPage.set(r.nextPage);
          this.hfHasMore.set(r.hasMore);
          this.searching.set(false);
          if (r.items.length > 0) this.selectHf(r.items[0]);
        },
        error: () => { this.searching.set(false); },
      });
    }
  }

  loadMore() {
    this.loadingMore.set(true);
    if (this.platform() === 'civitai') {
      this.civitaiService.search(
        this.query(), this.modelType(), 1, this.civitaiCursor(),
        this.civitaiBaseModel(), this.civitaiSort(), this.civitaiPeriod()
      ).subscribe({
        next: r => {
          this.civitaiResults.update(prev => [...prev, ...r.items]);
          this.civitaiCursor.set(r.metadata?.nextCursor ?? '');
          this.civitaiHasMore.set(!!r.metadata?.nextCursor);
          this.loadingMore.set(false);
        },
        error: () => { this.loadingMore.set(false); },
      });
    } else {
      this.hfService.search(this.query(), this.modelType(), this.hfPage(), this.hfSort(), -1, this.formatFilter()).subscribe({
        next: r => {
          this.hfResults.update(prev => [...prev, ...r.items]);
          this.hfPage.set(r.nextPage);
          this.hfHasMore.set(r.hasMore);
          this.loadingMore.set(false);
        },
        error: () => { this.loadingMore.set(false); },
      });
    }
  }

  selectCivitai(model: CivitaiModel) {
    const targetId = model.id;
    this.selectedModel.set(model);
    this.galleryIndex.set(0);
    this.versions.set([]);
    this.versionsError.set('');
    this.loadingVersions.set(true);
    this.selectedCivitaiFiles.set(new Map());
    this.civitaiService.getVersions(model.id).subscribe({
      next: v => {
        if (this.selectedModel()?.id !== targetId) return;
        this.versions.set(v.versions);
        this.loadingVersions.set(false);
      },
      error: err => {
        if (this.selectedModel()?.id !== targetId) return;
        this.versionsError.set(err?.error?.error ?? 'Failed to load versions');
        this.loadingVersions.set(false);
      },
    });
  }

  toggleCivitaiFile(versionId: number, file: CivitaiFile) {
    const key = `${versionId}_${file.id}`;
    this.selectedCivitaiFiles.update(prev => {
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
    this.dlService.startDownload(file.downloadUrl, this.modelType(), file.name, 'civitai', String(versionId)).subscribe();
  }

  downloadSelectedCivitai() {
    for (const { file, versionId } of this.selectedCivitaiFiles().values()) {
      this.dlService.startDownload(file.downloadUrl, this.modelType(), file.name, 'civitai', String(versionId)).subscribe();
    }
    this.selectedCivitaiFiles.set(new Map());
  }

  selectHf(model: HfModel) {
    const repoId = model.modelId ?? model.id;
    this.selectedHfModel.set(model);
    this.selectedHfRepoId.set(repoId);
    this.hfFiles.set([]);
    this.selectedHfFiles.set(new Set());
    this.hfService.getFiles(repoId).subscribe({
      next: files => {
        if (this.selectedHfRepoId() !== repoId) return;
        this.hfFiles.set(files);
      },
    });
  }

  toggleHfFile(filename: string) {
    this.selectedHfFiles.update(prev => {
      const next = new Set(prev);
      if (next.has(filename)) {
        next.delete(filename);
      } else {
        next.add(filename);
      }
      return next;
    });
  }

  isHfFileSelected(filename: string): boolean {
    return this.selectedHfFiles().has(filename);
  }

  downloadHf(file: { filename: string; size: number; url: string }) {
    this.dlService.startDownload(file.url, this.modelType(), file.filename, 'huggingface', this.selectedHfRepoId()).subscribe();
  }

  downloadSelectedHf() {
    const files = this.hfFiles();
    for (const filename of this.selectedHfFiles()) {
      const file = files.find(f => f.filename === filename);
      if (file) {
        this.dlService.startDownload(file.url, this.modelType(), file.filename, 'huggingface', this.selectedHfRepoId()).subscribe();
      }
    }
    this.selectedHfFiles.set(new Set());
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
    return (model.modelVersions?.[0]?.images ?? []).slice(0, 8).map(i => i.url).filter(Boolean);
  }

  isVideo(url: string): boolean {
    const lower = url.toLowerCase();
    return lower.includes('.mp4') || lower.includes('.webm') || lower.includes('.mov');
  }

  setGalleryIndex(i: number) { this.galleryIndex.set(i); }

  currentGalleryUrl(model: CivitaiModel): string {
    const images = this.civitaiGalleryImages(model);
    return images[this.galleryIndex()] ?? '';
  }

  civitaiModelBaseModel(model: CivitaiModel): string {
    return model.modelVersions?.[0]?.baseModel ?? '';
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
