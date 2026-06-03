import { Component, HostListener, OnInit, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { catchError, of } from 'rxjs';
import {
  ModelService,
  CatalogEntryDetail,
  RepoFile,
  ModelMeta,
  InstalledFile,
} from '../../services/model';
import { DownloadService } from '../../services/download';
import { WorkflowService } from '../../services/workflow';
import { NotificationService } from '../../services/notification';
import { SafeHtmlPipe } from '../../utils/safe-html.pipe';

const MEDIA_API = '/tiny-model-manager/api/media';

@Component({
  selector: 'app-catalog-detail',
  imports: [CommonModule, FormsModule, RouterLink, SafeHtmlPipe],
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

  primaryMeta = signal<ModelMeta | null>(null);
  primaryType = '';
  primaryPath = '';

  editMode = signal(false);
  saving = signal(false);
  refetching = signal(false);
  editMeta: Partial<ModelMeta> = {};
  newTriggerWord = '';
  newTag = '';
  copied = signal(false);
  galleryIdx = signal(0);
  lightboxOpen = signal(false);

  showUninstallConfirm = signal(false);
  deleting = signal(false);

  readonly sourceName = computed(() => {
    const p = this.platform;
    if (p === 'civitai') return 'CivitAI';
    if (p === 'huggingface') return 'HuggingFace';
    return 'source';
  });

  readonly downloadedFiles = computed(() =>
    (this.entry()?.repo_files ?? []).filter((f) => f.is_downloaded),
  );

  readonly notDownloadedFiles = computed(() =>
    (this.entry()?.repo_files ?? []).filter((f) => !f.is_downloaded),
  );

  readonly primaryFile = computed<InstalledFile | null>(
    () => this.entry()?.installed_files[0] ?? null,
  );

  readonly activeMedia = computed(() => {
    const m = this.primaryMeta();
    const idx = this.galleryIdx();
    if (!m?.media?.length) return null;
    return m.media[Math.min(idx, m.media.length - 1)];
  });

  @HostListener('document:keydown.escape')
  onEscapeKey() {
    if (this.lightboxOpen()) this.lightboxOpen.set(false);
  }

  constructor(
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly modelService: ModelService,
    private readonly downloadService: DownloadService,
    private readonly workflowService: WorkflowService,
    private readonly notifService: NotificationService,
  ) {}

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
        this.entry.set(data);
        this.loading.set(false);
        const first = data.installed_files[0];
        if (first) {
          this.primaryType = first.model_type;
          this.primaryPath = first.filename;
          this.loadPrimaryMeta();
        } else {
          this.primaryMeta.set(null);
          this.primaryType = '';
          this.primaryPath = '';
        }
      },
      error: (err) => {
        this.error.set((err as Error).message);
        this.loading.set(false);
      },
    });
  }

  private loadPrimaryMeta() {
    this.modelService
      .getMetadata(this.primaryType, this.primaryPath)
      .pipe(catchError(() => of(null)))
      .subscribe((meta) => {
        this.primaryMeta.set(meta);
        if (meta) this.syncEditMeta(meta);
      });
  }

  private syncEditMeta(m: ModelMeta) {
    this.editMeta = {
      description: m.description,
      trigger_words: [...m.trigger_words],
      tags: [...m.tags],
      base_model: m.base_model ?? '',
    };
  }

  enterEdit() {
    this.editMode.set(true);
  }

  cancelEdit() {
    const m = this.primaryMeta();
    if (m) this.syncEditMeta(m);
    this.editMode.set(false);
  }

  save() {
    this.saving.set(true);
    this.modelService
      .updateMetadataWithPath(this.primaryType, this.primaryPath, this.editMeta)
      .subscribe({
        next: (result) => {
          this.saving.set(false);
          this.notifService.show('success', 'Metadata saved.');
          const newPath = result.new_path;
          if (newPath !== this.primaryPath) {
            this.primaryPath = newPath;
          }
          this.editMode.set(false);
          const current = this.primaryMeta()!;
          this.primaryMeta.set({
            ...current,
            description: this.editMeta.description ?? current.description,
            trigger_words: this.editMeta.trigger_words ?? current.trigger_words,
            tags: this.editMeta.tags ?? current.tags,
            base_model: this.editMeta.base_model ?? current.base_model,
          });
        },
        error: (err) => {
          this.saving.set(false);
          this.notifService.show('error', (err as Error).message);
        },
      });
  }

  refetch() {
    this.refetching.set(true);
    this.modelService.refetchMetadata(this.primaryType, this.primaryPath).subscribe({
      next: (meta) => {
        this.primaryMeta.set(meta);
        this.syncEditMeta(meta);
        this.refetching.set(false);
        this.notifService.show('success', 'Metadata re-fetched.');
        this.load();
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
    const words = this.primaryMeta()?.trigger_words ?? [];
    if (!words.length) return;
    navigator.clipboard.writeText(words.join(', ')).then(() => {
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 2000);
    });
  }

  addFileToWorkflow(f: InstalledFile) {
    this.workflowService.addToWorkflow(f.model_type, f.filename).subscribe({
      next: () => this.notifService.show('success', 'Model queued for workflow insertion.'),
      error: () =>
        this.notifService.show('error', 'Failed to enqueue model for workflow insertion.'),
    });
  }

  uninstall() {
    this.deleting.set(true);
    this.modelService.deleteModel(this.primaryType, this.primaryPath).subscribe({
      next: () => {
        this.deleting.set(false);
        this.showUninstallConfirm.set(false);
        this.notifService.show('success', 'File uninstalled.');
        this.load();
      },
      error: (err) => {
        this.deleting.set(false);
        this.showUninstallConfirm.set(false);
        this.notifService.show('error', (err as Error).message);
      },
    });
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
    this.downloadingFiles.update((s) => new Set(s).add(file.filename));
    this.downloadService
      .startDownload(file.download_url, modelType, file.filename, platform)
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
