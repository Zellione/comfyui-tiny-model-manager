import { Component, OnInit, signal } from '@angular/core';
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
  editType = '';
  modelTypes = signal<string[]>([]);
  meta = signal<ModelMeta | null>(null);
  editMeta: Partial<ModelMeta> = {};
  newTriggerWord = '';
  newTag = '';
  loading = signal(true);
  saving = signal(false);
  refetching = signal(false);
  error = signal('');

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
        this.editMeta = {
          description: m.description,
          trigger_words: [...m.trigger_words],
          tags: [...m.tags],
          base_model: m.base_model ?? '',
        };
        this.editType = this.modelType;
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set((err as Error).message);
        this.loading.set(false);
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
        this.editMeta = {
          description: m.description,
          trigger_words: [...m.trigger_words],
          tags: [...m.tags],
          base_model: m.base_model ?? '',
        };
        this.editType = this.modelType;
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

  mediaUrl(path: string): string {
    return `/tiny-model-manager/api/media/${encodeURIComponent(path)}`;
  }
}
