import { Component, HostListener, OnInit, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { of } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { ModelService, ModelMeta } from '../../services/model';
import { WorkflowService } from '../../services/workflow';
import { NotificationService } from '../../services/notification';

@Component({
  selector: 'app-model-detail',
  imports: [CommonModule, FormsModule, RouterLink],
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
    if (m?.base_model) parts.push(m.base_model);
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

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private modelService: ModelService,
    private workflowService: WorkflowService,
    private notifService: NotificationService,
  ) {}

  ngOnInit() {
    this.modelType = this.route.snapshot.paramMap.get('type') ?? '';
    this.modelPath = this.route.snapshot.paramMap.get('path') ?? '';
    this.editType = this.modelType;
    this.modelService.getModelTypes().subscribe((types) => this.modelTypes.set(types));
    this.loadMeta();
  }

  loadMeta() {
    this.loading.set(true);
    this.modelService.getMetadata(this.modelType, this.modelPath).subscribe({
      next: (m) => {
        this.meta.set(m);
        this.syncEditMeta(m);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set((err as Error).message);
        this.loading.set(false);
      },
    });
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
      },
      error: (err) => {
        this.error.set((err as Error).message);
        this.refetching.set(false);
        this.notifService.show('error', (err as Error).message);
      },
    });
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
      next: () => this.router.navigate(['/models']),
      error: (err) => {
        this.deleting.set(false);
        this.showUninstallConfirm.set(false);
        this.notifService.show('error', (err as Error).message);
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
