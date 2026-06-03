import {
  Component,
  DestroyRef,
  HostListener,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { of } from 'rxjs';
import { catchError, filter, switchMap } from 'rxjs/operators';
import { ModelService, ModelMeta, RepoFile, CatalogEntryDetail } from '../../services/model';
import { DownloadService } from '../../services/download';
import { WorkflowService } from '../../services/workflow';
import { NotificationService } from '../../services/notification';
import { SafeHtmlPipe } from '../../utils/safe-html.pipe';

@Component({
  selector: 'app-model-detail',
  imports: [CommonModule, FormsModule, RouterLink, SafeHtmlPipe],
  templateUrl: './model-detail.html',
  styleUrl: './model-detail.scss',
})
export class ModelDetail implements OnInit {
  modelType = '';
  modelPath = '';
  get modelBasename(): string {
    return this.modelPath.split('/').pop() ?? this.modelPath;
  }
  editType = '';
  modelTypes = signal<string[]>([]);
  meta = signal<ModelMeta | null>(null);
  editMeta: Partial<ModelMeta> = {};
  newTriggerWord = '';
  newTag = '';
  loading = signal(true);
  saving = signal(false);
  refetching = signal(false);
  deleting = signal(false);
  error = signal('');
  editMode = signal(false);
  showUninstallConfirm = signal(false);
  galleryIdx = signal(0);
  copied = signal(false);
  lightboxOpen = signal(false);
  repoFiles = signal<RepoFile[]>([]);
  fileBaseModels = signal<Record<string, string>>({});
  pendingDeleteFile = signal<RepoFile | null>(null);
  downloadingFiles = signal<Set<string>>(new Set());
  catalogEntry = signal<CatalogEntryDetail | null>(null);
  linkSourceUrl = signal('');
  linking = signal(false);
  linkSourceError = signal('');

  readonly displayTitle = computed(() => this.catalogEntry()?.display_name || this.modelBasename);
  readonly showLinkSourcePanel = computed(() => !this.meta()?.source_url);

  @HostListener('document:keydown.escape')
  onEscapeKey() {
    if (this.lightboxOpen()) this.lightboxOpen.set(false);
  }

  readonly activeMedia = computed(() => {
    const m = this.meta();
    const idx = this.galleryIdx();
    if (!m?.media?.length) return null;
    return m.media[Math.min(idx, m.media.length - 1)];
  });

  readonly eyebrowParts = computed(() => {
    const parts: string[] = [];
    if (this.modelType) parts.push(this.modelType);
    const m = this.meta();
    const size = this.formatBytes(m?.size_bytes ?? 0);
    if (size) parts.push(size);
    return parts;
  });

  readonly sourceName = computed(() => {
    const platform = this.meta()?.source_platform;
    if (platform === 'civitai') return 'CivitAI';
    if (platform === 'huggingface') return 'HuggingFace';
    return 'source';
  });

  private readonly destroyRef = inject(DestroyRef);

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private modelService: ModelService,
    private downloadService: DownloadService,
    private workflowService: WorkflowService,
    private notifService: NotificationService,
  ) {}

  ngOnInit() {
    this.modelType = this.route.snapshot.paramMap.get('type') ?? '';
    this.modelPath = this.route.snapshot.paramMap.get('path') ?? '';
    this.editType = this.modelType;
    this.modelService.getModelTypes().subscribe((types) => this.modelTypes.set(types));
    this.loadMeta();
    this.downloadService.completedTasks$
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        filter((t) => t.status === 'done'),
      )
      .subscribe(() => this.loadRepoFiles());
  }

  loadMeta() {
    this.loading.set(true);
    this.modelService.getMetadata(this.modelType, this.modelPath).subscribe({
      next: (m) => {
        this.meta.set(m);
        this.syncEditMeta(m);
        this.loading.set(false);
        this.loadRepoFiles();
        this.loadCatalogEntry(m);
      },
      error: (err) => {
        this.error.set((err as Error).message);
        this.loading.set(false);
      },
    });
  }

  loadRepoFiles() {
    this.modelService
      .getRepoFiles(this.modelType, this.modelPath)
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

  private loadCatalogEntry(m: ModelMeta) {
    const platform = m.source_platform;
    const url = m.source_url;
    if (!platform || !url) return;
    let pageId = '';
    if (platform === 'huggingface') {
      pageId = url.replace('https://huggingface.co/', '');
    } else if (platform === 'civitai') {
      const match = /\/models\/(\d+)/.exec(url);
      pageId = match?.[1] ?? '';
    }
    if (!pageId) return;
    this.modelService
      .getCatalogEntry(platform, pageId)
      .pipe(catchError(() => of(null)))
      .subscribe((entry) => this.catalogEntry.set(entry));
  }

  private syncEditMeta(m: ModelMeta) {
    this.editMeta = {
      description: m.description,
      trigger_words: [...m.trigger_words],
      tags: [...m.tags],
      base_model: m.base_model ?? '',
    };
    this.editType = this.modelType;
  }

  enterEdit() {
    this.editMode.set(true);
  }

  cancelEdit() {
    const m = this.meta();
    if (m) this.syncEditMeta(m);
    this.editMode.set(false);
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

  save() {
    this.saving.set(true);
    this.error.set('');
    const typeChanged = !!this.editType && this.editType !== this.modelType;
    const move$ = typeChanged
      ? this.modelService.moveModel(this.modelType, this.modelPath, this.editType)
      : of(undefined as void);
    move$
      .pipe(
        switchMap(() => {
          if (typeChanged) this.modelType = this.editType;
          return this.modelService.updateMetadata(this.modelType, this.modelPath, this.editMeta);
        }),
      )
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.notifService.show('success', 'Metadata saved.');
          this.saveSiblingBaseModels();
          if (typeChanged) {
            this.router.navigate(['/models', this.modelType, this.modelPath]);
          } else {
            this.editMode.set(false);
            const current = this.meta()!;
            this.meta.set({
              ...current,
              description: this.editMeta.description ?? current.description,
              trigger_words: this.editMeta.trigger_words ?? current.trigger_words,
              tags: this.editMeta.tags ?? current.tags,
              base_model: this.editMeta.base_model ?? current.base_model,
            });
          }
        },
        error: (err) => {
          this.saving.set(false);
          this.error.set((err as Error).message);
          this.notifService.show('error', (err as Error).message);
        },
      });
  }

  refetch() {
    this.refetching.set(true);
    this.error.set('');
    this.modelService.refetchMetadata(this.modelType, this.modelPath).subscribe({
      next: (m) => {
        this.meta.set(m);
        this.syncEditMeta(m);
        this.refetching.set(false);
        this.notifService.show('success', 'Metadata re-fetched.');
        this.loadRepoFiles();
      },
      error: (err) => {
        this.error.set((err as Error).message);
        this.refetching.set(false);
        this.notifService.show('error', (err as Error).message);
      },
    });
  }

  private saveSiblingBaseModels() {
    const edits = this.fileBaseModels();
    for (const f of this.repoFiles()) {
      if (!f.is_downloaded) continue;
      const newVal = edits[f.filename];
      if (newVal === undefined || newVal === f.base_model) continue;
      const path = f.installed_path || f.filename;
      if (path === this.modelPath) continue; // current file is saved by the main save()
      this.modelService.updateMetadata(f.model_type, path, { base_model: newVal }).subscribe();
    }
  }

  addToWorkflow() {
    this.workflowService.addToWorkflow(this.modelType, this.modelPath).subscribe({
      next: () => this.notifService.show('success', 'Model queued for workflow insertion.'),
      error: () =>
        this.notifService.show('error', 'Failed to enqueue model for workflow insertion.'),
    });
  }

  uninstall() {
    this.deleting.set(true);
    this.modelService.deleteModel(this.modelType, this.modelPath).subscribe({
      next: () => {
        this.notifService.show('success', `${this.modelBasename} uninstalled.`);
        this.router.navigate(['/models']);
      },
      error: (err) => {
        this.deleting.set(false);
        this.showUninstallConfirm.set(false);
        this.notifService.show('error', (err as Error).message);
      },
    });
  }

  linkSource() {
    const url = this.linkSourceUrl().trim();
    if (!url) return;
    this.linking.set(true);
    this.linkSourceError.set('');
    this.modelService.linkSource(this.modelType, this.modelPath, url).subscribe({
      next: () => {
        this.linking.set(false);
        this.notifService.show('success', 'Source linked.');
        this.router.navigate(['/models']);
      },
      error: (err) => {
        this.linking.set(false);
        this.linkSourceError.set((err as Error).message);
      },
    });
  }

  addFileToWorkflow(file: RepoFile) {
    const path = file.installed_path || file.filename;
    this.workflowService.addToWorkflow(this.modelType, path).subscribe({
      next: () => this.notifService.show('success', 'Queued for workflow insertion.'),
      error: () => this.notifService.show('error', 'Failed to enqueue for workflow insertion.'),
    });
  }

  deleteFile(file: RepoFile) {
    const path = file.installed_path || file.filename;
    this.modelService.deleteModel(this.modelType, path).subscribe({
      next: () => {
        this.pendingDeleteFile.set(null);
        this.notifService.show('success', `${file.filename} deleted.`);
        this.loadRepoFiles();
      },
      error: (err) => this.notifService.show('error', (err as Error).message),
    });
  }

  downloadFile(file: RepoFile) {
    if (!file.download_url || this.downloadingFiles().has(file.filename)) return;
    const dir = this.modelPath.includes('/')
      ? this.modelPath.split('/').slice(0, -1).join('/') + '/'
      : '';
    const destFilename = dir + file.filename;
    const platform = this.meta()?.source_platform ?? '';
    let sourceId = '';
    if (platform === 'civitai') {
      const m = /\/api\/download\/models\/(\d+)/.exec(file.download_url);
      sourceId = m?.[1] ?? '';
    } else if (platform === 'huggingface') {
      sourceId = this.catalogEntry()?.source_page_id ?? '';
    }
    this.downloadingFiles.update((s) => new Set(s).add(file.filename));
    this.downloadService
      .startDownload(file.download_url, this.modelType, destFilename, platform, sourceId)
      .subscribe({
        next: () => {
          this.notifService.show('success', `Downloading ${file.filename}…`);
        },
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

  copyTriggerWords() {
    const text = (this.meta()?.trigger_words ?? []).join(', ');
    const done = () => {
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 1400);
    };
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(done).catch(done);
    } else {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand('copy');
      } finally {
        document.body.removeChild(ta);
      }
      done();
    }
  }

  mediaUrl(path: string): string {
    return `/tiny-model-manager/api/media/${encodeURIComponent(path)}`;
  }

  formatBytes(bytes: number): string {
    if (!bytes) return '';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i];
  }
}
