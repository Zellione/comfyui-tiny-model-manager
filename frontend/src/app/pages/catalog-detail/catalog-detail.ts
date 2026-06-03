import { Component, OnInit, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ModelService, CatalogEntryDetail, RepoFile } from '../../services/model';
import { DownloadService } from '../../services/download';
import { NotificationService } from '../../services/notification';

const MEDIA_API = '/tiny-model-manager/api/media';

@Component({
  selector: 'app-catalog-detail',
  imports: [CommonModule, RouterLink],
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

  constructor(
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly modelService: ModelService,
    private readonly downloadService: DownloadService,
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
      },
      error: (err) => {
        this.error.set((err as Error).message);
        this.loading.set(false);
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

  removeFromCatalog() {
    this.removing.set(true);
    this.modelService.removeCatalogEntry(this.platform, this.pageId).subscribe({
      next: () => {
        const name = this.entry()?.display_name || this.pageId;
        this.notifService.show('success', `Removed "${name}" from catalog.`);
        this.router.navigate(['/models']);
      },
      error: (err) => {
        this.removing.set(false);
        this.showRemoveConfirm.set(false);
        this.notifService.show('error', 'Failed to remove from catalog: ' + (err as Error).message);
      },
    });
  }
}
