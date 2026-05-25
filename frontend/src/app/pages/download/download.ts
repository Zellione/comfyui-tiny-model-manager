import { Component, signal, inject, computed, DestroyRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { toSignal, takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject } from 'rxjs';
import { debounceTime, distinctUntilChanged, switchMap, of, catchError } from 'rxjs';
import { DownloadService, DownloadTask } from '../../services/download';
import { CivitaiService, CivitaiModel, CivitaiVersion, CivitaiFile, CivitaiDirectLinkInfo } from '../../services/civitai';
import { HuggingFaceService, HfModel } from '../../services/huggingface';
import { detectLink, LinkKind } from '../../utils/link-detector';

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
  private destroyRef = inject(DestroyRef);
  private pasteUrl$ = new Subject<string>();

  platform = signal<Platform>('civitai');
  query = signal('');
  modelType = signal<ModelType>('checkpoints');
  modelTypes: ModelType[] = ['checkpoints', 'loras', 'embeddings', 'vae', 'controlnet'];

  // Paste-a-link section
  pasteUrl      = signal('');
  linkKind      = signal<LinkKind>({ type: 'empty' });
  linkModelType = signal<ModelType>('checkpoints');
  linkResolving = signal(false);
  linkError     = signal('');
  linkResolved  = signal<CivitaiDirectLinkInfo | null>(null);
  linkImages    = signal<string[]>([]);

  hfResolveKind       = computed(() => { const k = this.linkKind(); return k.type === 'hf-resolve' ? k : null; });
  civitaiDownloadKind = computed(() => { const k = this.linkKind(); return k.type === 'civitai-download' ? k : null; });
  canSubmitLink       = computed(() => {
    const k = this.linkKind();
    if (k.type === 'hf-resolve') return true;
    if (k.type === 'civitai-download') return !!this.linkResolved() && !this.linkResolving();
    return false;
  });

  civitaiResults = signal<CivitaiModel[]>([]);
  hfResults = signal<HfModel[]>([]);
  activeTasks = toSignal(this.dlService.activeTasks$, { initialValue: [] as DownloadTask[] });

  selectedModel = signal<CivitaiModel | null>(null);
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
          if (kind.type === 'hf-resolve') {
            this.linkResolving.set(true);
            return this.hfService.resolveDirectLink(kind.repo).pipe(
              catchError(() => of({ image_urls: [] as string[] }))
            );
          }
          if (kind.type === 'civitai-download') {
            this.linkResolving.set(true);
            return this.civitaiService.resolveDirectLink(kind.versionId).pipe(
              catchError(err => {
                this.linkError.set(err?.error?.error ?? 'Failed to resolve link');
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
          if ('filename' in result) {
            this.linkResolved.set(result as CivitaiDirectLinkInfo);
            this.linkModelType.set((result.model_type as ModelType) ?? 'checkpoints');
          }
          this.linkImages.set(result.image_urls ?? []);
        }
        this.linkResolving.set(false);
      });
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

  search() {
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
      this.civitaiService.search(this.query(), this.modelType()).subscribe({
        next: r => {
          this.civitaiResults.set(r.items);
          this.civitaiCursor.set(r.metadata?.nextCursor ?? '');
          this.civitaiHasMore.set(!!r.metadata?.nextCursor);
          this.searching.set(false);
        },
        error: () => { this.searching.set(false); },
      });
    } else {
      this.hfService.search(this.query(), this.modelType(), 0).subscribe({
        next: r => {
          this.hfResults.set(r.items);
          this.hfPage.set(r.nextPage);
          this.hfHasMore.set(r.hasMore);
          this.searching.set(false);
        },
        error: () => { this.searching.set(false); },
      });
    }
  }

  loadMore() {
    this.loadingMore.set(true);
    if (this.platform() === 'civitai') {
      this.civitaiService.search(this.query(), this.modelType(), 1, this.civitaiCursor()).subscribe({
        next: r => {
          this.civitaiResults.update(prev => [...prev, ...r.items]);
          this.civitaiCursor.set(r.metadata?.nextCursor ?? '');
          this.civitaiHasMore.set(!!r.metadata?.nextCursor);
          this.loadingMore.set(false);
        },
        error: () => { this.loadingMore.set(false); },
      });
    } else {
      this.hfService.search(this.query(), this.modelType(), this.hfPage()).subscribe({
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
    this.selectedModel.set(model);
    this.versions.set([]);
    this.versionsError.set('');
    this.loadingVersions.set(true);
    this.selectedCivitaiFiles.set(new Map());
    this.civitaiService.getVersions(model.id).subscribe({
      next: v => { this.versions.set(v); this.loadingVersions.set(false); },
      error: err => {
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
    this.selectedHfRepoId.set(repoId);
    this.hfFiles.set([]);
    this.selectedHfFiles.set(new Set());
    this.hfService.getFiles(repoId).subscribe({
      next: files => this.hfFiles.set(files),
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

  onImgError(event: Event) {
    (event.target as HTMLImageElement).style.display = 'none';
  }
}
