import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { KeywordsService } from '../../services/keywords';
import { FilenameKeyword } from '../../utils/filename-detector';
import { MODEL_TYPES, ModelType } from '../../utils/model-types';
import { NotificationService } from '../../services/notification';
import { SettingsService } from '../../services/settings';

@Component({
  selector: 'app-settings',
  imports: [CommonModule, FormsModule, TranslatePipe],
  templateUrl: './settings.html',
  styleUrl: './settings.scss',
})
export class Settings implements OnInit {
  private readonly keywordsService = inject(KeywordsService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly notifService = inject(NotificationService);
  private readonly translate = inject(TranslateService);
  private readonly settingsService = inject(SettingsService);

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

  missingModelsIntegration = signal(true);
  integrationLoading = signal(true);

  ngOnInit() {
    this.load();
    this.loadIntegrationSetting();
  }

  private loadIntegrationSetting() {
    this.settingsService
      .getSettings()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (s) => {
          this.missingModelsIntegration.set(s.missing_models_integration ?? true);
          this.integrationLoading.set(false);
        },
        error: () => this.integrationLoading.set(false),
      });
  }

  setMissingModelsIntegration(enabled: boolean) {
    const previous = this.missingModelsIntegration();
    this.missingModelsIntegration.set(enabled);
    this.settingsService
      .updateSettings({ missing_models_integration: enabled })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        // An open ComfyUI tab listens on this channel and starts/stops injecting live.
        next: () => this.broadcast(enabled),
        error: () => {
          this.missingModelsIntegration.set(previous);
          this.notifService.show(
            'error',
            this.translate.instant('settings.integration.error_save'),
          );
        },
      });
  }

  private broadcast(value: boolean) {
    const channel = new BroadcastChannel('tmm');
    channel.postMessage({ key: 'missing_models_integration', value });
    channel.close();
  }

  private load() {
    this.loading.set(true);
    this.error.set('');
    this.keywordsService
      .getKeywords()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (kws) => {
          this.keywords.set(kws);
          this.loading.set(false);
        },
        error: () => {
          this.error.set(this.translate.instant('settings.keywords.error_load'));
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
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.editingId.set(null);
          this.load();
        },
        error: () => {
          this.saving.set(false);
          this.notifService.show('error', this.translate.instant('settings.keywords.error_save'));
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
      .pipe(takeUntilDestroyed(this.destroyRef))
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
          this.notifService.show('error', this.translate.instant('settings.keywords.error_add'));
        },
      });
  }

  deleteKeyword(id: number) {
    this.keywordsService
      .deleteKeyword(id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => this.load(),
        error: () =>
          this.notifService.show('error', this.translate.instant('settings.keywords.error_delete')),
      });
  }
}
