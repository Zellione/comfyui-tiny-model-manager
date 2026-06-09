import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { KeywordsService } from '../../services/keywords';
import { FilenameKeyword } from '../../utils/filename-detector';
import { MODEL_TYPES, ModelType } from '../../utils/model-types';
import { NotificationService } from '../../services/notification';

@Component({
  selector: 'app-settings',
  imports: [CommonModule, FormsModule],
  templateUrl: './settings.html',
  styleUrl: './settings.scss',
})
export class Settings implements OnInit {
  private readonly keywordsService = inject(KeywordsService);
  private readonly notifService = inject(NotificationService);

  readonly modelTypes = MODEL_TYPES;

  keywords = signal<FilenameKeyword[]>([]);
  loading = signal(true);
  saving = signal(false);
  error = signal('');

  editingId = signal<number | null>(null);
  editKeyword = signal('');
  editBaseModel = signal('');
  editModelType = signal('');

  newKeyword = signal('');
  newBaseModel = signal('');
  newModelType = signal('');
  adding = signal(false);

  ngOnInit() {
    this.load();
  }

  private load() {
    this.loading.set(true);
    this.error.set('');
    this.keywordsService.getKeywords().subscribe({
      next: (kws) => {
        this.keywords.set(kws);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Failed to load keywords');
        this.loading.set(false);
      },
    });
  }

  startEdit(kw: FilenameKeyword) {
    this.editingId.set(kw.id);
    this.editKeyword.set(kw.keyword);
    this.editBaseModel.set(kw.base_model ?? '');
    this.editModelType.set(kw.model_type ?? '');
  }

  cancelEdit() {
    this.editingId.set(null);
  }

  saveEdit() {
    const id = this.editingId();
    const keyword = this.editKeyword().trim();
    if (!id || !keyword) return;
    this.saving.set(true);
    this.keywordsService
      .updateKeyword(
        id,
        keyword,
        this.editBaseModel().trim() || null,
        (this.editModelType() as ModelType) || null,
      )
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.editingId.set(null);
          this.load();
        },
        error: () => {
          this.saving.set(false);
          this.notifService.show('error', 'Failed to save keyword');
        },
      });
  }

  addKeyword() {
    const keyword = this.newKeyword().trim();
    if (!keyword) return;
    this.adding.set(true);
    this.keywordsService
      .createKeyword(
        keyword,
        this.newBaseModel().trim() || null,
        (this.newModelType() as ModelType) || null,
      )
      .subscribe({
        next: () => {
          this.adding.set(false);
          this.newKeyword.set('');
          this.newBaseModel.set('');
          this.newModelType.set('');
          this.load();
        },
        error: () => {
          this.adding.set(false);
          this.notifService.show('error', 'Failed to add keyword');
        },
      });
  }

  deleteKeyword(id: number) {
    this.keywordsService.deleteKeyword(id).subscribe({
      next: () => this.load(),
      error: () => this.notifService.show('error', 'Failed to delete keyword'),
    });
  }
}
