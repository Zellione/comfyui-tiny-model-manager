import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ModelService, ModelMeta } from '../../services/model';

@Component({
  selector: 'app-model-detail',
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './model-detail.html',
  styleUrl: './model-detail.scss',
})
export class ModelDetail implements OnInit {
  modelType = '';
  modelPath = '';
  meta: ModelMeta | null = null;
  editMeta: Partial<ModelMeta> = {};
  newTriggerWord = '';
  loading = true;
  saving = false;
  error = '';
  saved = false;

  constructor(private route: ActivatedRoute, private modelService: ModelService) {}

  ngOnInit() {
    this.modelType = this.route.snapshot.paramMap.get('type') ?? '';
    this.modelPath = this.route.snapshot.paramMap.get('path') ?? '';
    this.loadMeta();
  }

  loadMeta() {
    this.loading = true;
    this.modelService.getMetadata(this.modelType, this.modelPath).subscribe({
      next: m => {
        this.meta = m;
        this.editMeta = { description: m.description, trigger_words: [...m.trigger_words] };
        this.loading = false;
      },
      error: err => {
        this.error = err.message;
        this.loading = false;
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

  save() {
    this.saving = true;
    this.saved = false;
    this.modelService.updateMetadata(this.modelType, this.modelPath, this.editMeta).subscribe({
      next: () => { this.saving = false; this.saved = true; },
      error: err => { this.saving = false; this.error = err.message; },
    });
  }

  mediaUrl(path: string): string {
    return `/tiny-model-manager/api/media/${encodeURIComponent(path)}`;
  }
}
