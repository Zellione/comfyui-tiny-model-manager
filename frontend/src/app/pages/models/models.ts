import { Component, OnInit, DestroyRef, signal, computed, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { forkJoin, merge, timer, Subject, EMPTY } from 'rxjs';
import { switchMap, catchError } from 'rxjs/operators';
import {
  ModelService,
  ModelFile,
  ModelMeta,
  CatalogEntry,
  CatalogListResponse,
} from '../../services/model';
import { WorkflowService } from '../../services/workflow';
import { NotificationService } from '../../services/notification';
import { SettingsService } from '../../services/settings';

const MEDIA_API = '/tiny-model-manager/api/media';
const UNKNOWN_BASE_MODEL = '__unknown__';
const UNKNOWN_SOURCE = '__unknown_source__';

@Component({
  selector: 'app-models',
  imports: [CommonModule, RouterLink],
  templateUrl: './models.html',
  styleUrl: './models.scss',
})
export class Models implements OnInit {
  catalogEntries = signal<CatalogEntry[]>([]);
  unknownFiles = signal<Record<string, ModelFile[]>>({});
  loading = signal(true);
  error = signal('');
  queuedForWorkflow = signal<Set<string>>(new Set());

  baseModelFilter = signal('');
  formatFilter = signal('');
  sourceFilter = signal('');
  sortBy = signal('name-asc');
  tagFilter = signal<string[]>([]);
  tagInput = signal('');
  showEmpty = signal(false);

  readonly sourceOptions = [
    { label: 'All sources', value: '' },
    { label: 'CivitAI', value: 'civitai' },
    { label: 'HuggingFace', value: 'huggingface' },
    { label: 'Unknown', value: '__unknown_source__' },
  ];
  readonly sortOptions = [
    { label: 'Name A→Z', value: 'name-asc' },
    { label: 'Name Z→A', value: 'name-desc' },
    { label: 'Date added (newest)', value: 'created-desc' },
    { label: 'Date added (oldest)', value: 'created-asc' },
  ];

  availableBaseModels = computed(() => {
    const values = new Set<string>();
    for (const e of this.catalogEntries()) {
      if (e.base_model) values.add(e.base_model);
    }
    return [...values].sort();
  });

  filteredEntries = computed(() => {
    const bm = this.baseModelFilter();
    const source = this.sourceFilter();
    const sort = this.sortBy();
    const showEmpty = this.showEmpty();
    let list = this.catalogEntries();

    if (!showEmpty) list = list.filter((e) => !e.is_empty);

    if (bm === UNKNOWN_BASE_MODEL) {
      list = list.filter((e) => !e.base_model);
    } else if (bm) {
      list = list.filter((e) => e.base_model === bm);
    }

    if (source === UNKNOWN_SOURCE) {
      list = list.filter((e) => !e.source_platform);
    } else if (source) {
      list = list.filter((e) => e.source_platform === source);
    }

    list = [...list].sort((a, b) => {
      switch (sort) {
        case 'name-asc':
          return this.cardTitle(a).localeCompare(this.cardTitle(b));
        case 'name-desc':
          return this.cardTitle(b).localeCompare(this.cardTitle(a));
        case 'created-desc':
          return Date.parse(b.created_at) - Date.parse(a.created_at);
        case 'created-asc':
          return Date.parse(a.created_at) - Date.parse(b.created_at);
        default:
          return 0;
      }
    });

    return list;
  });

  filteredEntriesByType = computed(() => {
    const out: Record<string, CatalogEntry[]> = {};
    for (const e of this.filteredEntries()) {
      const t = e.model_type || 'other';
      if (!out[t]) out[t] = [];
      out[t].push(e);
    }
    return out;
  });

  filteredTypeKeys = computed(() => Object.keys(this.filteredEntriesByType()));

  hasActiveFilters = computed(
    () => !!this.baseModelFilter() || !!this.formatFilter() || !!this.sourceFilter(),
  );

  hasAnyEntries = computed(() => this.catalogEntries().length > 0);
  hasAnyUnknown = computed(() => Object.keys(this.unknownFiles()).length > 0);
  hasAnyContent = computed(() => this.hasAnyEntries() || this.hasAnyUnknown());
  unknownTypeKeys = computed(() => Object.keys(this.unknownFiles()));

  organizeEnabled = signal(false);
  pendingFilenames = signal<Set<string>>(new Set());

  // Legacy: keep modelsByType for the organize feature
  modelsByType = signal<Record<string, ModelFile[]>>({});

  private destroyRef = inject(DestroyRef);
  private pollTrigger = new Subject<void>();

  constructor(
    private modelService: ModelService,
    private workflowService: WorkflowService,
    private notifService: NotificationService,
    private settingsService: SettingsService,
  ) {}

  ngOnInit() {
    this.load();
    this.startQueuePoll();
    this.settingsService.getOrganizeEnabled().subscribe((v) => this.organizeEnabled.set(v));

    const channel = new BroadcastChannel('tmm');
    channel.onmessage = () => {
      this.settingsService.getOrganizeEnabled().subscribe((v) => this.organizeEnabled.set(v));
      this.pollTrigger.next();
    };
    this.destroyRef.onDestroy(() => channel.close());
  }

  load() {
    this.loading.set(true);
    this.modelService.listCatalog().subscribe({
      next: (data: CatalogListResponse) => {
        this.catalogEntries.set(data.entries);
        this.unknownFiles.set(data.unknown_files);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(err.message);
        this.loading.set(false);
      },
    });
  }

  private startQueuePoll() {
    merge(timer(0, 2000), this.pollTrigger)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        switchMap(() => this.modelService.getPendingQueue().pipe(catchError(() => EMPTY))),
      )
      .subscribe((filenames: string[]) => {
        const prev = this.pendingFilenames();
        const next = new Set(filenames);
        this.pendingFilenames.set(next);
        if (prev.size > 0 && next.size < prev.size) {
          this.load();
        }
      });
  }

  isPending(filename: string): boolean {
    return this.pendingFilenames().has(filename);
  }

  clearAllFilters() {
    this.baseModelFilter.set('');
    this.formatFilter.set('');
    this.sourceFilter.set('');
    this.tagFilter.set([]);
    this.tagInput.set('');
  }

  basename(path: string): string {
    return path.split('/').pop() ?? path;
  }

  formatSize(bytes: number): string {
    if (bytes >= 1e9) return (bytes / 1e9).toFixed(1) + ' GB';
    if (bytes >= 1e6) return (bytes / 1e6).toFixed(1) + ' MB';
    return (bytes / 1e3).toFixed(0) + ' KB';
  }

  cardTitle(entry: CatalogEntry): string {
    if (entry.display_name) return entry.display_name;
    if (entry.installed_files.length > 0) {
      const fname = entry.installed_files[0].filename.split('/').pop() ?? '';
      return fname.replace(/\.[^.]+$/, '').replace(/[_-]/g, ' ');
    }
    if (entry.source_platform === 'huggingface') {
      const parts = entry.source_page_id.split('/');
      return parts.at(-1) ?? '';
    }
    return entry.source_page_id;
  }

  cardDetailRoute(entry: CatalogEntry): string[] {
    if (entry.source_platform && entry.source_page_id) {
      return ['/catalog', entry.source_platform];
    }
    if (entry.installed_files[0]) {
      return ['/models', entry.installed_files[0].model_type, entry.installed_files[0].filename];
    }
    return ['/catalog'];
  }

  cardDetailQuery(entry: CatalogEntry): Record<string, string> | null {
    if (entry.source_platform && entry.source_page_id) {
      return { pageId: entry.source_page_id };
    }
    return null;
  }

  catalogThumbnailUrl(entry: CatalogEntry): string | null {
    if (!entry.thumbnail_url) return null;
    return `${MEDIA_API}/${encodeURIComponent(entry.thumbnail_url)}`;
  }

  unknownThumbnailUrl(meta?: ModelMeta): string | null {
    const img = meta?.media?.find((m) => m.media_type === 'image');
    return img ? `${MEDIA_API}/${encodeURIComponent(img.local_path)}` : null;
  }

  entryFileCount(entry: CatalogEntry): number {
    return entry.installed_files.length;
  }

  addToWorkflow(type: string, filename: string) {
    this.workflowService.addToWorkflow(type, filename).subscribe({
      next: () => {
        const s = new Set(this.queuedForWorkflow());
        s.add(filename);
        this.queuedForWorkflow.set(s);
        setTimeout(() => {
          const s2 = new Set(this.queuedForWorkflow());
          s2.delete(filename);
          this.queuedForWorkflow.set(s2);
        }, 2000);
        this.notifService.show('success', 'Model queued for workflow insertion.');
      },
      error: () =>
        this.notifService.show('error', 'Failed to enqueue model for workflow insertion.'),
    });
  }

  deleteUnknownModel(type: string, file: ModelFile) {
    if (!confirm(`Delete ${file.filename}?`)) return;
    this.modelService.deleteModel(type, file.filename).subscribe({
      next: () => {
        this.notifService.show('success', `Deleted: ${file.filename}`);
        this.load();
      },
      error: (err) => this.notifService.show('error', 'Delete failed: ' + (err as Error).message),
    });
  }

  deleteSelectedUnknown(type: string, files: ModelFile[]) {
    if (!files.length) return;
    if (!confirm(`Delete ${files.length} model(s)?`)) return;
    forkJoin(files.map((f) => this.modelService.deleteModel(type, f.filename))).subscribe({
      next: () => {
        this.notifService.show('success', `Deleted ${files.length} model(s).`);
        this.load();
      },
      error: (err) => this.notifService.show('error', 'Delete failed: ' + (err as Error).message),
    });
  }

  organizeIntoSubfolders() {
    if (!confirm('Reorganize all installed models into base-model subfolders?')) return;
    this.modelService.organizeIntoSubfolders().subscribe({
      next: (r) => {
        this.notifService.show(
          'success',
          `Organized ${r.moved} model(s). Skipped: ${r.skipped}. Errors: ${r.errors}.`,
        );
        this.load();
      },
      error: (err) =>
        this.notifService.show('error', 'Organization failed: ' + (err as Error).message),
    });
  }
}
