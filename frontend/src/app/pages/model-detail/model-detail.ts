import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ModelService, ModelMeta } from '../../services/model';
import { WorkflowService } from '../../services/workflow';

@Component({
  selector: 'app-model-detail',
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './model-detail.html',
  styleUrl: './model-detail.scss',
})
export class ModelDetail implements OnInit {
  modelType = '';
  modelPath = '';
  meta = signal<ModelMeta | null>(null);
  editMeta: Partial<ModelMeta> = {};
  newTriggerWord = '';
  newTag = '';
  loading = signal(true);
  saving = signal(false);
  refetching = signal(false);
  error = signal('');
  saved = signal(false);

  constructor(
    private route: ActivatedRoute,
    private modelService: ModelService,
    private workflowService: WorkflowService,
  ) {}

  ngOnInit() {
    this.modelType = this.route.snapshot.paramMap.get('type') ?? '';
    this.modelPath = this.route.snapshot.paramMap.get('path') ?? '';
    this.loadMeta();
  }

  loadMeta() {
    this.loading.set(true);
    this.modelService.getMetadata(this.modelType, this.modelPath).subscribe({
      next: m => {
        this.meta.set(m);
        this.editMeta = { description: m.description, trigger_words: [...m.trigger_words], tags: [...m.tags], base_model: m.base_model ?? '' };
        this.loading.set(false);
      },
      error: err => {
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
    this.editMeta.trigger_words = (this.editMeta.trigger_words ?? []).filter(w => w !== word);
  }

  addTag() {
    const t = this.newTag.trim();
    if (!t) return;
    this.editMeta.tags = [...(this.editMeta.tags ?? []), t];
    this.newTag = '';
  }

  removeTag(tag: string) {
    this.editMeta.tags = (this.editMeta.tags ?? []).filter(t => t !== tag);
  }

  save() {
    this.saving.set(true);
    this.saved.set(false);
    this.modelService.updateMetadata(this.modelType, this.modelPath, this.editMeta).subscribe({
      next: () => { this.saving.set(false); this.saved.set(true); },
      error: err => { this.saving.set(false); this.error.set((err as Error).message); },
    });
  }

  refetch() {
    this.refetching.set(true);
    this.error.set('');
    this.modelService.refetchMetadata(this.modelType, this.modelPath).subscribe({
      next: m => {
        this.meta.set(m);
        this.editMeta = { description: m.description, trigger_words: [...m.trigger_words], tags: [...m.tags], base_model: m.base_model ?? '' };
        this.refetching.set(false);
      },
      error: err => { this.error.set((err as Error).message); this.refetching.set(false); },
    });
  }

  addToWorkflow() {
    this.workflowService.addToWorkflow(this.modelType, this.modelPath).subscribe({
      error: () => alert('Failed to enqueue model for workflow insertion.'),
    });
  }

  mediaUrl(path: string): string {
    return `/tiny-model-manager/api/media/${encodeURIComponent(path)}`;
  }
}
