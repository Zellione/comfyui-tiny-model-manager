import { Component, OnInit, DestroyRef, signal, computed, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { forkJoin, merge, timer, Subject, EMPTY } from 'rxjs';
import { switchMap, catchError } from 'rxjs/operators';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import {
  ModelService,
  ModelFile,
  ModelMeta,
  CatalogEntry,
  CatalogListResponse,
  UnregisteredFile,
  RegisterModelRequest,
} from '../../services/model';
import { WorkflowService, isWorkflowInsertable } from '../../services/workflow';
import { NotificationService } from '../../services/notification';
import { SettingsService } from '../../services/settings';
import { formatSize } from '../../utils/format';
import { mediaUrl } from '../../utils/media';
import { ConfirmPopover } from '../../components/confirm-popover/confirm-popover';
import {
  FilePickerPopover,
  PickableFile,
} from '../../components/file-picker-popover/file-picker-popover';
const UNKNOWN_BASE_MODEL = '__unknown__';
const UNKNOWN_SOURCE = '__unknown_source__';

const LINK_ERROR_KEYS: Record<string, string> = {
  invalid_url: 'models.unregistered.link_invalid',
  not_found: 'models.unregistered.link_not_found',
  provider_unavailable: 'models.unregistered.link_unavailable',
};

interface RegisterForm {
  modelType: string;
  baseModel: string;
  description: string;
  tags: string;
  saving: boolean;
  error: string;
  hashStatus: 'loading' | 'found' | 'not_found' | 'error';
  name: string;
  link: string;
  linkStatus: 'idle' | 'loading' | 'found' | 'error';
  linkMessage: string;
}

@Component({
  selector: 'app-models',
  imports: [CommonModule, RouterLink, ConfirmPopover, FilePickerPopover, TranslatePipe],
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
    { label: 'models.source.all', value: '' },
    { label: 'CivitAI', value: 'civitai' },
    { label: 'HuggingFace', value: 'huggingface' },
    { label: 'models.source.unknown', value: '__unknown_source__' },
  ];
  readonly sortOptions = [
    { label: 'models.sort.name_asc', value: 'name-asc' },
    { label: 'models.sort.name_desc', value: 'name-desc' },
    { label: 'models.sort.created_desc', value: 'created-desc' },
    { label: 'models.sort.created_asc', value: 'created-asc' },
  ];

  availableBaseModels = computed(() => {
    const values = new Set<string>();
    for (const e of this.catalogEntries()) {
      if (e.base_model) values.add(e.base_model);
    }
    return [...values].sort((a, b) => a.localeCompare(b));
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

  unregisteredFiles = signal<Record<string, UnregisteredFile[]>>({});
  unregisteredTypeKeys = computed(() => Object.keys(this.unregisteredFiles()));
  hasAnyUnregistered = computed(() => this.unregisteredTypeKeys().length > 0);
  scanLoading = signal(false);
  unregisteredExpanded = signal(false);
  registerFormFile = signal<{ type: string; file: UnregisteredFile } | null>(null);
  registerForm = signal<RegisterForm>({
    modelType: '',
    baseModel: '',
    description: '',
    tags: '',
    saving: false,
    error: '',
    hashStatus: 'loading',
    name: '',
    link: '',
    linkStatus: 'idle',
    linkMessage: '',
  });

  private readonly registerFileHash = signal<string>('');
  private readonly registerSource = signal<{
    platform: string;
    source_id: string;
    civitai_model_id: string;
  } | null>(null);

  private readonly destroyRef = inject(DestroyRef);
  private readonly pollTrigger = new Subject<void>();

  constructor(
    private readonly modelService: ModelService,
    private readonly workflowService: WorkflowService,
    private readonly notifService: NotificationService,
    private readonly settingsService: SettingsService,
    private readonly translate: TranslateService,
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

  formatSize = formatSize;

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
    return mediaUrl(entry.thumbnail_url);
  }

  unknownThumbnailUrl(meta?: ModelMeta): string | null {
    const img = meta?.media?.find((m) => m.media_type === 'image');
    return img ? mediaUrl(img.local_path) : null;
  }

  entryFileCount(entry: CatalogEntry): number {
    return entry.installed_files.length;
  }

  // Only files whose type the ComfyUI extension can turn into a loader node. Anything else
  // would be queued and then silently skipped, leaving the card stuck as "processing".
  insertableFiles(entry: CatalogEntry): PickableFile[] {
    return entry.installed_files.filter((f) => isWorkflowInsertable(f.model_type));
  }

  canInsert(modelType: string): boolean {
    return isWorkflowInsertable(modelType);
  }

  isQueued(filename: string): boolean {
    return this.queuedForWorkflow().has(filename);
  }

  addFileToWorkflow(file: PickableFile) {
    this.addToWorkflow(file.model_type, file.filename);
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
        this.notifService.show('success', this.translate.instant('models.notify.queued'));
      },
      error: () =>
        this.notifService.show('error', this.translate.instant('models.notify.queue_failed')),
    });
  }

  deleteUnknownModel(type: string, file: ModelFile) {
    this.modelService.deleteModel(type, file.filename).subscribe({
      next: () => {
        this.notifService.show(
          'success',
          this.translate.instant('models.notify.deleted', { filename: file.filename }),
        );
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

  async copyTriggerWords(entry: CatalogEntry) {
    const text = (entry.trigger_words ?? []).join(', ');
    try {
      await navigator.clipboard.writeText(text);
      this.notifService.show('success', this.translate.instant('models.notify.trigger_copied'));
    } catch {
      this.notifService.show('error', this.translate.instant('models.notify.trigger_copy_failed'));
    }
  }

  onImgLoad(event: Event) {
    (event.target as HTMLImageElement).style.display = 'block';
  }

  onImgError(event: Event) {
    (event.target as HTMLImageElement).style.display = 'none';
  }

  videoPosterUrl(localPath: string): string {
    return `/tiny-model-manager/api/media-poster/${encodeURIComponent(localPath)}`;
  }

  onVideoPosterLoad(event: Event) {
    const img = event.target as HTMLImageElement;
    img.style.display = 'block';
    const fallback = img.previousElementSibling as HTMLElement | null;
    if (fallback) fallback.style.display = 'none';
  }

  organizeIntoSubfolders() {
    this.modelService.organizeIntoSubfolders().subscribe({
      next: (r) => {
        this.notifService.show(
          'success',
          this.translate.instant('models.notify.organized', {
            moved: r.moved,
            skipped: r.skipped,
            errors: r.errors,
          }),
        );
        this.load();
      },
      error: (err) =>
        this.notifService.show('error', 'Organization failed: ' + (err as Error).message),
    });
  }

  scan(): void {
    this.scanLoading.set(true);
    this.modelService.getUnregistered().subscribe({
      next: (data) => {
        this.unregisteredFiles.set(data);
        this.unregisteredExpanded.set(true);
        this.scanLoading.set(false);
      },
      error: () => {
        this.scanLoading.set(false);
        this.notifService.show('error', this.translate.instant('models.unregistered.scan_failed'));
      },
    });
  }

  toggleUnregistered(): void {
    this.unregisteredExpanded.update((v) => !v);
  }

  openRegisterForm(type: string, file: UnregisteredFile): void {
    this.registerFormFile.set({ type, file });
    this.registerForm.set({
      modelType: type,
      baseModel: '',
      description: '',
      tags: '',
      saving: false,
      error: '',
      hashStatus: 'loading',
      name: '',
      link: '',
      linkStatus: 'idle',
      linkMessage: '',
    });
    this.registerFileHash.set('');
    this.registerSource.set(null);
    this._runHashLookup(file.filename, type);
  }

  cancelRegister(): void {
    this.registerFormFile.set(null);
  }

  private _runHashLookup(filename: string, modelType: string): void {
    this.modelService.hashLookup(filename, modelType).subscribe({
      next: (result) => {
        this.registerFileHash.set(result.hash);
        if (result.match && result.metadata) {
          const m = result.metadata;
          this.registerSource.set({
            platform: 'civitai',
            source_id: m.civitai_version_id,
            civitai_model_id: m.civitai_model_id,
          });
          this.registerForm.update((f) => ({
            ...f,
            hashStatus: 'found',
            name: m.name,
            baseModel: m.base_model,
            description: m.description,
            tags: m.tags.join(', '),
          }));
        } else {
          this.registerForm.update((f) => ({ ...f, hashStatus: 'not_found' }));
        }
      },
      error: () => {
        this.registerForm.update((f) => ({ ...f, hashStatus: 'error' }));
      },
    });
  }

  retryHashLookup(): void {
    const formFile = this.registerFormFile();
    if (!formFile) return;
    this.registerForm.update((f) => ({ ...f, hashStatus: 'loading', error: '' }));
    this._runHashLookup(formFile.file.filename, formFile.type);
  }

  resolveLink(): void {
    const url = this.registerForm().link.trim();
    if (!url) return;
    this.registerForm.update((f) => ({ ...f, linkStatus: 'loading', linkMessage: '' }));
    this.modelService.resolveLink(url).subscribe({
      next: (result) => {
        const m = result.metadata;
        this.registerSource.set({
          platform: result.platform,
          source_id: result.source_id,
          civitai_model_id: m.civitai_model_id,
        });
        this.registerForm.update((f) => ({
          ...f,
          name: m.name,
          baseModel: m.base_model,
          description: m.description,
          tags: m.tags.join(', '),
          linkStatus: 'found',
          linkMessage: this.translate.instant('models.unregistered.link_found', {
            platform: result.platform,
          }),
        }));
      },
      error: (err) => {
        const key = LINK_ERROR_KEYS[err?.error?.error] ?? 'models.unregistered.link_failed';
        this.registerForm.update((f) => ({
          ...f,
          linkStatus: 'error',
          linkMessage: this.translate.instant(key),
        }));
      },
    });
  }

  submitRegister(): void {
    const formFile = this.registerFormFile();
    if (!formFile) return;
    const form = this.registerForm();
    const req: RegisterModelRequest = {
      filename: formFile.file.filename,
      model_type: form.modelType,
    };
    if (form.baseModel) req.base_model = form.baseModel;
    if (form.description) req.description = form.description;
    const tags = form.tags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);
    if (tags.length > 0) req.tags = tags;

    const hash = this.registerFileHash();
    if (hash) req.file_hash = hash;

    const source = this.registerSource();
    if (source) {
      req.source_platform = source.platform;
      req.source_id = source.source_id;
      req.civitai_model_id = source.civitai_model_id;
    }

    this.registerForm.update((f) => ({ ...f, saving: true, error: '' }));
    this.modelService.registerModel(req).subscribe({
      next: () => {
        const mtype = formFile.type;
        const fname = formFile.file.filename;
        this.unregisteredFiles.update((prev) => {
          const updated = { ...prev };
          updated[mtype] = (updated[mtype] ?? []).filter((f) => f.filename !== fname);
          if (updated[mtype].length === 0) delete updated[mtype];
          return updated;
        });
        this.registerFormFile.set(null);
        this.load();
      },
      error: (err) => {
        const msg =
          err?.error?.error === 'file_not_found'
            ? this.translate.instant('models.unregistered.file_gone')
            : this.translate.instant('models.unregistered.register_failed');
        this.registerForm.update((f) => ({ ...f, saving: false, error: msg }));
      },
    });
  }
}
