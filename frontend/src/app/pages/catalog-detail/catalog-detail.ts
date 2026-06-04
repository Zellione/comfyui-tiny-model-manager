import {
  Component,
  DestroyRef,
  HostListener,
  OnInit,
  Signal,
  computed,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Observable, catchError, forkJoin, of } from 'rxjs';
import { toSignal, takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  ModelService,
  CatalogEntryDetail,
  RepoFile,
  ModelMeta,
  InstalledFile,
} from '../../services/model';
import { DownloadService, DownloadTask } from '../../services/download';
import { WorkflowService } from '../../services/workflow';
import { NotificationService } from '../../services/notification';
import { SafeHtmlPipe } from '../../utils/safe-html.pipe';
import { BaseModelSelect } from '../../components/base-model-select/base-model-select';

const MEDIA_API = '/tiny-model-manager/api/media';

@Component({
  selector: 'app-catalog-detail',
  imports: [CommonModule, FormsModule, RouterLink, SafeHtmlPipe, BaseModelSelect],
  templateUrl: './catalog-detail.html',
  styleUrl: './catalog-detail.scss',
})
export class CatalogDetail implements OnInit {
  platform = '';
  pageId = '';

  entry = signal<CatalogEntryDetail | null>(null);
  loading = signal(true);
  error = signal('');
  removing = signal(false);
  showRemoveConfirm = signal(false);
  downloadingFiles = signal<Set<string>>(new Set());

  // The currently-installed file used to load the per-file base-model editor (repoFiles).
  primaryType = '';
  primaryPath = '';

  editMode = signal(false);
  saving = signal(false);
  refetching = signal(false);
  editMeta: Partial<ModelMeta> = {};
  // Fully-populated repo files (includes base_model per installed file), loaded from the
  // /repo-files endpoint. Used by the edit panel's per-file base-model list.
  repoFiles = signal<RepoFile[]>([]);
  fileBaseModels = signal<Record<string, string>>({});
  newTriggerWord = '';
  newTag = '';
  copied = signal(false);
  galleryIdx = signal(0);
  lightboxOpen = signal(false);

  pendingUninstallRepoFile = signal<RepoFile | null>(null);
  deleting = signal(false);

  // Files whose download has completed but whose backend post-processing (metadata
  // fetch, subfolder move, catalog linking) is still in flight. The row shows a
  // "Processing…" state and is silently re-polled until is_downloaded flips true.
  finalizingFiles = signal<Set<string>>(new Set());
  private finalizeTimers = new Set<ReturnType<typeof setTimeout>>();

  readonly activeTasks: Signal<DownloadTask[]>;

  readonly activeTaskMap = computed(() => {
    const map = new Map<string, DownloadTask>();
    for (const t of this.activeTasks()) {
      map.set(t.filename, t);
    }
    return map;
  });

  readonly sourceName = computed(() => {
    const p = this.platform;
    if (p === 'civitai') return 'CivitAI';
    if (p === 'huggingface') return 'HuggingFace';
    return 'source';
  });

  readonly downloadedFiles = computed(() =>
    (this.entry()?.repo_files ?? []).filter((f) => f.is_downloaded),
  );

  // Downloaded files from the rich /repo-files list (carry base_model); drives the
  // per-file base-model editor. Keyed consistently with fileBaseModels.
  readonly editableFiles = computed(() => this.repoFiles().filter((f) => f.is_downloaded));

  readonly notDownloadedFiles = computed(() =>
    (this.entry()?.repo_files ?? []).filter((f) => !f.is_downloaded),
  );

  readonly primaryFile = computed<InstalledFile | null>(
    () => this.entry()?.installed_files[0] ?? null,
  );

  // The catalog entry owns its source-page metadata; the view always shows the entry's
  // own values (never the installed model's).
  readonly displayDescription = computed(() => this.entry()?.description ?? '');
  readonly displayTriggerWords = computed(() => this.entry()?.trigger_words ?? []);
  readonly displayTags = computed(() => this.entry()?.tags ?? []);
  readonly displayMedia = computed(() => this.entry()?.media ?? []);

  readonly activeMedia = computed(() => {
    const media = this.displayMedia();
    const idx = this.galleryIdx();
    if (!media.length) return null;
    return media[Math.min(idx, media.length - 1)];
  });

  @HostListener('document:keydown.escape')
  onEscapeKey() {
    if (this.lightboxOpen()) this.lightboxOpen.set(false);
    else if (this.pendingUninstallRepoFile()) this.pendingUninstallRepoFile.set(null);
  }

  constructor(
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly modelService: ModelService,
    private readonly downloadService: DownloadService,
    private readonly workflowService: WorkflowService,
    private readonly notifService: NotificationService,
    private readonly destroyRef: DestroyRef,
  ) {
    this.activeTasks = toSignal(this.downloadService.activeTasks$, {
      initialValue: [] as DownloadTask[],
    });

    this.downloadService.completedTasks$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((task) => {
        const entry = this.entry();
        if (!entry?.repo_files.some((rf) => rf.filename === task.filename)) return;
        // The download is no longer in the queued/downloading phase.
        this.downloadingFiles.update((s) => {
          const next = new Set(s);
          next.delete(task.filename);
          return next;
        });
        if (task.status === 'error') {
          this.notifService.show('error', `Download failed: ${task.error ?? task.filename}`);
          this.load();
          return;
        }
        // The file is on disk, but backend post-processing (metadata, subfolder move,
        // catalog linking) runs asynchronously and may briefly leave is_downloaded false.
        // Show a "Processing…" state and re-poll until the file is confirmed.
        this.finalizingFiles.update((s) => new Set(s).add(task.filename));
        this.pollUntilDownloaded(task.filename);
      });

    this.destroyRef.onDestroy(() => {
      for (const t of this.finalizeTimers) clearTimeout(t);
      this.finalizeTimers.clear();
    });
  }

  private static readonly FINALIZE_MAX_ATTEMPTS = 30;
  private static readonly FINALIZE_INTERVAL_MS = 2000;

  private pollUntilDownloaded(filename: string, attempt = 0) {
    this.modelService.getCatalogEntry(this.platform, this.pageId).subscribe({
      next: (data) => {
        this.applyEntry(data);
        const rf = data.repo_files.find((r) => r.filename === filename);
        if (rf?.is_downloaded || attempt + 1 >= CatalogDetail.FINALIZE_MAX_ATTEMPTS) {
          this.finalizingFiles.update((s) => {
            const next = new Set(s);
            next.delete(filename);
            return next;
          });
          return;
        }
        const timer = setTimeout(() => {
          this.finalizeTimers.delete(timer);
          this.pollUntilDownloaded(filename, attempt + 1);
        }, CatalogDetail.FINALIZE_INTERVAL_MS);
        this.finalizeTimers.add(timer);
      },
      error: () => {
        this.finalizingFiles.update((s) => {
          const next = new Set(s);
          next.delete(filename);
          return next;
        });
      },
    });
  }

  ngOnInit() {
    this.platform = this.route.snapshot.paramMap.get('platform') ?? '';
    this.pageId = this.route.snapshot.queryParamMap.get('pageId') ?? '';
    this.load();
  }

  load() {
    this.loading.set(true);
    this.error.set('');
    this.modelService.getCatalogEntry(this.platform, this.pageId).subscribe({
      next: (data) => {
        this.loading.set(false);
        this.applyEntry(data);
      },
      error: (err) => {
        this.error.set((err as Error).message);
        this.loading.set(false);
      },
    });
  }

  private applyEntry(data: CatalogEntryDetail) {
    this.entry.set(data);
    const first = data.installed_files[0];
    if (first) {
      this.primaryType = first.model_type;
      this.primaryPath = first.filename;
      this.loadRepoFiles();
    } else {
      this.primaryType = '';
      this.primaryPath = '';
      this.repoFiles.set([]);
      this.fileBaseModels.set({});
    }
    this.syncEditMeta();
  }

  private loadRepoFiles() {
    this.modelService
      .getRepoFiles(this.primaryType, this.primaryPath)
      .pipe(catchError(() => of([] as RepoFile[])))
      .subscribe((files) => {
        this.repoFiles.set(files);
        const bm: Record<string, string> = {};
        for (const f of files) {
          if (f.is_downloaded) bm[f.filename] = f.base_model ?? '';
        }
        this.fileBaseModels.set(bm);
      });
  }

  setFileBaseModel(filename: string, value: string) {
    this.fileBaseModels.update((m) => ({ ...m, [filename]: value }));
  }

  // Editing targets the catalog entry's own metadata; seed the form from its values.
  private syncEditMeta() {
    this.editMeta = {
      description: this.displayDescription(),
      trigger_words: [...this.displayTriggerWords()],
      tags: [...this.displayTags()],
    };
  }

  enterEdit() {
    this.editMode.set(true);
  }

  cancelEdit() {
    this.syncEditMeta();
    // Discard unsaved per-file base-model edits.
    const bm: Record<string, string> = {};
    for (const f of this.repoFiles()) {
      if (f.is_downloaded) bm[f.filename] = f.base_model ?? '';
    }
    this.fileBaseModels.set(bm);
    this.editMode.set(false);
  }

  save() {
    this.saving.set(true);
    // Description, trigger words and tags are saved on the catalog entry itself (so they
    // persist with zero files installed). base_model is set per file (and may move the
    // file into a subfolder) and is handled by the per-file updates below.
    const metaOp = this.modelService.updateCatalogMetadata(this.platform, this.pageId, {
      description: this.editMeta.description ?? '',
      trigger_words: this.editMeta.trigger_words ?? [],
      tags: this.editMeta.tags ?? [],
    });
    forkJoin([metaOp, ...this.collectBaseModelUpdates()]).subscribe({
      next: () => {
        this.saving.set(false);
        this.notifService.show('success', 'Metadata saved.');
        this.editMode.set(false);
        // Reload so moved files land under their new subfolders and the catalog reflects it.
        this.load();
      },
      error: (err) => {
        this.saving.set(false);
        this.notifService.show('error', (err as Error).message);
      },
    });
  }

  // Builds an update request for every downloaded file whose base model changed. The
  // backend moves the file into the matching subfolder and updates the DB record.
  private collectBaseModelUpdates(): Observable<unknown>[] {
    const edits = this.fileBaseModels();
    const ops: Observable<unknown>[] = [];
    for (const f of this.repoFiles()) {
      if (!f.is_downloaded) continue;
      const newVal = edits[f.filename];
      if (newVal === undefined || newVal === (f.base_model ?? '')) continue;
      const path = f.installed_path || f.filename;
      ops.push(this.modelService.updateMetadata(f.model_type, path, { base_model: newVal }));
    }
    return ops;
  }

  refetch() {
    this.refetching.set(true);
    this.modelService.refetchCatalog(this.platform, this.pageId).subscribe({
      next: (entry) => {
        this.refetching.set(false);
        this.applyEntry(entry);
        this.notifService.show('success', 'Metadata re-fetched from source.');
      },
      error: (err) => {
        this.refetching.set(false);
        this.notifService.show('error', (err as Error).message);
      },
    });
  }

  addTriggerWord() {
    const w = this.newTriggerWord.trim();
    if (!w) return;
    this.editMeta.trigger_words = [...(this.editMeta.trigger_words ?? []), w];
    this.newTriggerWord = '';
  }

  removeTriggerWord(word: string) {
    this.editMeta.trigger_words = (this.editMeta.trigger_words ?? []).filter((w) => w !== word);
  }

  addTag() {
    const t = this.newTag.trim();
    if (!t) return;
    this.editMeta.tags = [...(this.editMeta.tags ?? []), t];
    this.newTag = '';
  }

  removeTag(tag: string) {
    this.editMeta.tags = (this.editMeta.tags ?? []).filter((t) => t !== tag);
  }

  copyTriggerWords() {
    const words = this.displayTriggerWords();
    if (!words.length) return;
    navigator.clipboard.writeText(words.join(', ')).then(() => {
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 2000);
    });
  }

  modelDetailUrl(type: string, path: string): string {
    return '/models/' + type + '/' + encodeURIComponent(path);
  }

  uninstallRepoFile() {
    const rf = this.pendingUninstallRepoFile();
    if (!rf) return;
    const path = rf.installed_path || rf.filename;
    this.deleting.set(true);
    this.modelService.deleteModel(rf.model_type, path).subscribe({
      next: () => {
        this.deleting.set(false);
        this.pendingUninstallRepoFile.set(null);
        this.notifService.show('success', 'File uninstalled.');
        this.load();
      },
      error: (err) => {
        this.deleting.set(false);
        this.pendingUninstallRepoFile.set(null);
        this.notifService.show('error', (err as Error).message);
      },
    });
  }

  addRepoFileToWorkflow(rf: RepoFile) {
    const path = rf.installed_path || rf.filename;
    this.workflowService.addToWorkflow(rf.model_type, path).subscribe({
      next: () => this.notifService.show('success', 'Model queued for workflow insertion.'),
      error: () =>
        this.notifService.show('error', 'Failed to enqueue model for workflow insertion.'),
    });
  }

  repoFileSubLabel(rf: RepoFile): string {
    const path = rf.installed_path || rf.filename;
    const subfolder = path.includes('/') ? path.split('/').slice(0, -1).join('/') : '';
    return subfolder ? `${rf.model_type} · ${subfolder}` : rf.model_type;
  }

  repoFileFullSubLabel(rf: RepoFile): string {
    if (rf.is_downloaded) {
      const label = this.repoFileSubLabel(rf);
      const size = rf.size_bytes ? this.formatBytes(rf.size_bytes) : '';
      return size ? `${label} · ${size}` : label;
    }
    return rf.size_bytes ? this.formatBytes(rf.size_bytes) : '';
  }

  activeTaskForFile(rf: RepoFile): DownloadTask | undefined {
    const task = this.activeTaskMap().get(rf.filename);
    if (!task) return undefined;
    // Only surface tasks that are actively in progress — done/error tasks persist in
    // the backend's in-memory store indefinitely and would show stale state on page load.
    return task.status === 'queued' || task.status === 'downloading' ? task : undefined;
  }

  private repoFileSourceId(rf: RepoFile, platform: string): string {
    if (platform === 'huggingface') {
      return this.entry()?.source_page_id ?? '';
    }
    if (platform === 'civitai' && rf.source_page_url) {
      try {
        return new URL(rf.source_page_url).searchParams.get('modelVersionId') ?? '';
      } catch {
        return '';
      }
    }
    return '';
  }

  removeFromCatalog() {
    this.removing.set(true);
    this.modelService.removeCatalogEntry(this.platform, this.pageId).subscribe({
      next: () => {
        const name = this.entry()?.display_name || this.pageId;
        this.notifService.show('success', `Removed "${name}" from catalog.`);
        this.router.navigate(['/catalog']);
      },
      error: (err) => {
        this.removing.set(false);
        this.showRemoveConfirm.set(false);
        this.notifService.show('error', 'Failed to remove from catalog: ' + (err as Error).message);
      },
    });
  }

  downloadFile(file: RepoFile) {
    if (!file.download_url || this.downloadingFiles().has(file.filename)) return;
    const e = this.entry();
    const platform = e?.source_platform ?? '';
    const modelType = file.model_type || 'checkpoints';
    const sourceId = this.repoFileSourceId(file, platform);
    this.downloadingFiles.update((s) => new Set(s).add(file.filename));
    this.downloadService
      .startDownload(file.download_url, modelType, file.filename, platform, sourceId)
      .subscribe({
        next: () => this.notifService.show('success', `Downloading ${file.filename}…`),
        error: () => {
          this.downloadingFiles.update((s) => {
            const next = new Set(s);
            next.delete(file.filename);
            return next;
          });
          this.notifService.show('error', `Failed to start download for ${file.filename}`);
        },
      });
  }

  mediaUrl(path: string): string {
    return `${MEDIA_API}/${encodeURIComponent(path)}`;
  }

  formatBytes(bytes: number | null): string {
    if (!bytes) return '';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i];
  }
}
