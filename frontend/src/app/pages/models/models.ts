import { Component, OnInit, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import { ModelService, ModelFile, ModelMeta } from '../../services/model';
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
  modelsByType = signal<Record<string, ModelFile[]>>({});
  loading = signal(true);
  error = signal('');
  selected = signal<Set<string>>(new Set());
  queuedForWorkflow = signal<Set<string>>(new Set());

  baseModelFilter = signal('');
  formatFilter = signal('');
  sourceFilter = signal('');
  sortBy = signal('name-asc');
  tagFilter = signal<string[]>([]);
  tagInput = signal('');

  readonly sourceOptions = [
    { label: 'All sources', value: '' },
    { label: 'CivitAI', value: 'civitai' },
    { label: 'HuggingFace', value: 'huggingface' },
    { label: 'Unknown', value: '__unknown_source__' },
  ];
  readonly formatOptions = [
    { label: 'All formats', value: '' },
    { label: '.safetensors', value: '.safetensors' },
    { label: '.gguf', value: '.gguf' },
    { label: '.ckpt', value: '.ckpt' },
    { label: '.pt', value: '.pt' },
    { label: '.bin', value: '.bin' },
  ];
  readonly sortOptions = [
    { label: 'Name A→Z', value: 'name-asc' },
    { label: 'Name Z→A', value: 'name-desc' },
    { label: 'Size (largest)', value: 'size-desc' },
    { label: 'Size (smallest)', value: 'size-asc' },
    { label: 'Date added (newest)', value: 'created-desc' },
    { label: 'Date added (oldest)', value: 'created-asc' },
    { label: 'Recently modified', value: 'modified-desc' },
  ];

  availableBaseModels = computed(() => {
    const values = new Set<string>();
    for (const files of Object.values(this.modelsByType())) {
      for (const f of files) {
        if (f.metadata?.base_model) values.add(f.metadata.base_model);
      }
    }
    return [...values].sort();
  });

  availableTags = computed(() => {
    const values = new Set<string>();
    for (const files of Object.values(this.modelsByType())) {
      for (const f of files) {
        for (const t of f.metadata?.tags ?? []) values.add(t);
      }
    }
    return [...values].sort();
  });

  tagSuggestions = computed(() => {
    const input = this.tagInput().toLowerCase().trim();
    if (!input) return [];
    const active = new Set(this.tagFilter());
    return this.availableTags()
      .filter((t) => t.toLowerCase().includes(input) && !active.has(t))
      .slice(0, 8);
  });

  filteredModelsByType = computed(() => {
    const bm = this.baseModelFilter();
    const fmt = this.formatFilter();
    const source = this.sourceFilter();
    const sort = this.sortBy();
    const tags = this.tagFilter();
    const raw = this.modelsByType();
    const out: Record<string, ModelFile[]> = {};

    for (const [type, files] of Object.entries(raw)) {
      let list = files as ModelFile[];

      if (bm === UNKNOWN_BASE_MODEL) {
        list = list.filter((f) => !f.metadata?.base_model);
      } else if (bm) {
        list = list.filter((f) => f.metadata?.base_model === bm);
      }

      if (fmt) list = list.filter((f) => f.filename.toLowerCase().endsWith(fmt));

      if (source === UNKNOWN_SOURCE) {
        list = list.filter((f) => !f.metadata?.source_platform);
      } else if (source) {
        list = list.filter((f) => f.metadata?.source_platform === source);
      }

      if (tags.length > 0) {
        list = list.filter((f) => tags.every((t) => f.metadata?.tags?.includes(t)));
      }

      list = [...list].sort((a, b) => {
        switch (sort) {
          case 'name-asc':
            return a.filename.localeCompare(b.filename);
          case 'name-desc':
            return b.filename.localeCompare(a.filename);
          case 'size-desc':
            return b.size_bytes - a.size_bytes;
          case 'size-asc':
            return a.size_bytes - b.size_bytes;
          case 'created-desc': {
            const ta = a.metadata?.created_at
              ? Date.parse(a.metadata.created_at)
              : a.modified_at * 1000;
            const tb = b.metadata?.created_at
              ? Date.parse(b.metadata.created_at)
              : b.modified_at * 1000;
            return tb - ta;
          }
          case 'created-asc': {
            const ta = a.metadata?.created_at
              ? Date.parse(a.metadata.created_at)
              : a.modified_at * 1000;
            const tb = b.metadata?.created_at
              ? Date.parse(b.metadata.created_at)
              : b.modified_at * 1000;
            return ta - tb;
          }
          case 'modified-desc':
            return b.modified_at - a.modified_at;
          default:
            return 0;
        }
      });

      if (list.length > 0) out[type] = list;
    }
    return out;
  });

  filteredTypeKeys = computed(() => Object.keys(this.filteredModelsByType()));
  hasActiveFilters = computed(
    () =>
      !!this.baseModelFilter() ||
      !!this.formatFilter() ||
      !!this.sourceFilter() ||
      this.tagFilter().length > 0,
  );
  hasAnyModels = computed(() => Object.keys(this.modelsByType()).length > 0);
  hasAnySelected = computed(() => this.selected().size > 0);
  totalSelected = computed(() => this.selected().size);
  organizeEnabled = signal(false);

  constructor(
    private modelService: ModelService,
    private workflowService: WorkflowService,
    private notifService: NotificationService,
    private settingsService: SettingsService,
  ) {}

  ngOnInit() {
    this.load();
    this.settingsService.getOrganizeEnabled().subscribe((v) => this.organizeEnabled.set(v));
  }

  load() {
    this.loading.set(true);
    this.selected.set(new Set());
    this.modelService.listModels().subscribe({
      next: (data) => {
        this.modelsByType.set(data);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(err.message);
        this.loading.set(false);
      },
    });
  }

  addTag(tag: string) {
    const t = tag.trim();
    if (!t || this.tagFilter().includes(t)) return;
    this.tagFilter.update((tags) => [...tags, t]);
    this.tagInput.set('');
  }

  addTagFromInput() {
    const suggestions = this.tagSuggestions();
    const raw = this.tagInput().trim();
    if (suggestions.length > 0) {
      this.addTag(suggestions[0]);
    } else if (raw) {
      this.addTag(raw);
    }
  }

  removeTag(tag: string) {
    this.tagFilter.update((tags) => tags.filter((t) => t !== tag));
  }

  clearAllFilters() {
    this.baseModelFilter.set('');
    this.formatFilter.set('');
    this.sourceFilter.set('');
    this.tagFilter.set([]);
    this.tagInput.set('');
  }

  formatSize(bytes: number): string {
    if (bytes >= 1e9) return (bytes / 1e9).toFixed(1) + ' GB';
    if (bytes >= 1e6) return (bytes / 1e6).toFixed(1) + ' MB';
    return (bytes / 1e3).toFixed(0) + ' KB';
  }

  thumbnailUrl(meta?: ModelMeta): string | null {
    const img = meta?.media?.find((m) => m.media_type === 'image');
    return img ? `${MEDIA_API}/${encodeURIComponent(img.local_path)}` : null;
  }

  private selectionKey(type: string, filename: string): string {
    return `${type}::${filename}`;
  }

  isSelected(type: string, filename: string): boolean {
    return this.selected().has(this.selectionKey(type, filename));
  }

  toggleSelect(type: string, filename: string) {
    const key = this.selectionKey(type, filename);
    const s = new Set(this.selected());
    if (s.has(key)) {
      s.delete(key);
    } else {
      s.add(key);
    }
    this.selected.set(s);
  }

  selectedForType(type: string): string[] {
    const prefix = `${type}::`;
    return [...this.selected()]
      .filter((k) => k.startsWith(prefix))
      .map((k) => k.slice(prefix.length));
  }

  deleteModel(type: string, file: ModelFile) {
    if (!confirm(`Delete ${file.filename}?`)) return;
    this.modelService.deleteModel(type, file.filename).subscribe({
      next: () => {
        this.notifService.show('success', `Deleted: ${file.filename}`);
        this.load();
      },
      error: (err) => this.notifService.show('error', 'Delete failed: ' + (err as Error).message),
    });
  }

  isQueuedForWorkflow(filename: string): boolean {
    return this.queuedForWorkflow().has(filename);
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

  deleteSelected(type: string) {
    const files = this.selectedForType(type);
    if (!files.length) return;
    if (!confirm(`Delete ${files.length} model(s)?`)) return;
    forkJoin(files.map((f) => this.modelService.deleteModel(type, f))).subscribe({
      next: () => {
        this.notifService.show('success', `Deleted ${files.length} model(s).`);
        this.load();
      },
      error: (err) => this.notifService.show('error', 'Delete failed: ' + (err as Error).message),
    });
  }

  clearSelection() {
    this.selected.set(new Set());
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

  deleteAllSelected() {
    const byType: Record<string, string[]> = {};
    for (const key of this.selected()) {
      const sep = key.indexOf('::');
      const type = key.slice(0, sep);
      const filename = key.slice(sep + 2);
      if (!byType[type]) byType[type] = [];
      byType[type].push(filename);
    }
    const total = this.selected().size;
    if (!confirm(`Delete ${total} model(s)?`)) return;
    const deletes = Object.entries(byType).flatMap(([type, files]) =>
      files.map((f) => this.modelService.deleteModel(type, f)),
    );
    forkJoin(deletes).subscribe({
      next: () => {
        this.notifService.show('success', `Deleted ${total} model(s).`);
        this.load();
      },
      error: (err) => this.notifService.show('error', 'Delete failed: ' + (err as Error).message),
    });
  }
}
