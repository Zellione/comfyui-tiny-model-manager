import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { of } from 'rxjs';
import { catchError, filter, switchMap } from 'rxjs/operators';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import {
  ModelService,
  ModelMeta,
  RepoFile,
  CatalogEntryDetail,
  RefetchPreviewResponse,
} from '../../services/model';
import { DownloadService } from '../../services/download';
import { WorkflowService } from '../../services/workflow';
import { NotificationService } from '../../services/notification';
import { KeywordsService } from '../../services/keywords';
import { detectFromFilename, FilenameKeyword } from '../../utils/filename-detector';
import { SafeHtmlPipe } from '../../utils/safe-html.pipe';
import { formatBytes } from '../../utils/format';
import { BaseModelSelect } from '../../components/base-model-select/base-model-select';
import { EditMetaForm } from '../../components/edit-meta-form/edit-meta-form';
import { RefetchReviewModal } from '../../components/refetch-review-modal/refetch-review-modal';
import { MediaGallery, GalleryMedia } from '../../components/media-gallery/media-gallery';
import { ConfirmPopover } from '../../components/confirm-popover/confirm-popover';

@Component({
  selector: 'app-model-detail',
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    SafeHtmlPipe,
    BaseModelSelect,
    EditMetaForm,
    RefetchReviewModal,
    MediaGallery,
    ConfirmPopover,
    TranslatePipe,
  ],
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
  loading = signal(true);
  saving = signal(false);
  refetching = signal(false);
  deleting = signal(false);
  error = signal('');
  editMode = signal(false);
  copied = signal(false);
  repoFiles = signal<RepoFile[]>([]);
  fileBaseModels = signal<Record<string, string>>({});
  downloadingFiles = signal<Set<string>>(new Set());
  catalogEntry = signal<CatalogEntryDetail | null>(null);
  linkSourceUrl = signal('');
  linking = signal(false);
  linkSourceError = signal('');
  refetchPreviewData = signal<RefetchPreviewResponse | null>(null);
  showRefetchModal = signal(false);
  refetchNoChanges = signal(false);
  readonly uploadBusy = signal(false);
  readonly uploadError = signal('');

  /**
   * Uploading is offered while nothing but the user's own images is on show — an empty
   * gallery included. A fetched preview means the model already has artwork.
   */
  readonly canUpload = computed(() => (this.meta()?.media ?? []).every((m) => m.uploaded));

  readonly displayTitle = computed(() => this.catalogEntry()?.display_name || this.modelBasename);
  readonly showLinkSourcePanel = computed(() => !this.meta()?.source_url);

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

  private readonly destroyRef = inject(DestroyRef);
  private readonly keywordsService = inject(KeywordsService);
  private readonly keywords = toSignal(this.keywordsService.getKeywords(), {
    initialValue: [] as FilenameKeyword[],
  });

  constructor(
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly modelService: ModelService,
    private readonly downloadService: DownloadService,
    private readonly workflowService: WorkflowService,
    private readonly notifService: NotificationService,
    private readonly translate: TranslateService,
  ) {}

  private detect(filename: string) {
    return detectFromFilename(filename, this.keywords());
  }

  ngOnInit() {
    this.modelType = this.route.snapshot.paramMap.get('type') ?? '';
    this.modelPath = decodeURIComponent(this.route.snapshot.paramMap.get('path') ?? '');
    this.editType = this.modelType;
    this.modelService
      .getModelTypes()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((types) => this.modelTypes.set(types));
    this.loadMeta();
    this.downloadService.completedTasks$
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        filter((t) => t.status === 'done'),
      )
      .subscribe(() => this.loadRepoFiles());
  }

  loadMeta() {
    this.loading.set(true);
    this.modelService
      .getMetadata(this.modelType, this.modelPath)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (m) => {
          this.meta.set(m);
          this.syncEditMeta(m);
          this.loading.set(false);
          this.loadRepoFiles();
          this.loadCatalogEntry(m);
        },
        error: (err) => {
          this.error.set((err as Error).message);
          this.loading.set(false);
        },
      });
  }

  loadRepoFiles() {
    this.modelService
      .getRepoFiles(this.modelType, this.modelPath)
      .pipe(catchError(() => of([] as RepoFile[])))
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((files) => {
        this.repoFiles.set(files);
        const bm: Record<string, string> = {};
        for (const f of files) {
          if (f.is_downloaded) bm[f.filename] = f.base_model ?? '';
        }
        this.fileBaseModels.set(bm);
      });
  }

  setFileBaseModel(filename: string, value: string) {
    this.fileBaseModels.update((m) => ({ ...m, [filename]: value }));
  }

  private loadCatalogEntry(m: ModelMeta) {
    const platform = m.source_platform;
    const url = m.source_url;
    if (!platform || !url) return;
    let pageId = '';
    if (platform === 'huggingface') {
      pageId = url.replace('https://huggingface.co/', '');
    } else if (platform === 'civitai') {
      const match = /\/models\/(\d+)/.exec(url);
      pageId = match?.[1] ?? '';
    }
    if (!pageId) return;
    this.modelService
      .getCatalogEntry(platform, pageId)
      .pipe(catchError(() => of(null)))
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((entry) => this.catalogEntry.set(entry));
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

  save() {
    this.saving.set(true);
    this.error.set('');
    const typeChanged = !!this.editType && this.editType !== this.modelType;
    const move$ = typeChanged
      ? this.modelService.moveModel(this.modelType, this.modelPath, this.editType)
      : of<void>(undefined);
    move$
      .pipe(
        switchMap(() => {
          if (typeChanged) this.modelType = this.editType;
          return this.modelService.updateMetadataWithPath(
            this.modelType,
            this.modelPath,
            this.editMeta,
          );
        }),
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          this.saving.set(false);
          this.notifService.show('success', this.translate.instant('model_detail.notify.saved'));
          this.saveSiblingBaseModels();
          const newPath = result.new_path;
          if (typeChanged || newPath !== this.modelPath) {
            this.modelPath = newPath;
            this.router.navigateByUrl(
              '/models/' + this.modelType + '/' + encodeURIComponent(newPath),
            );
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

  triggerRefetchPreview() {
    this.refetching.set(true);
    this.error.set('');
    this.refetchNoChanges.set(false);
    this.modelService
      .refetchPreview(this.modelType, this.modelPath)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.refetching.set(false);
          if (res.removed) {
            this.notifService.show(
              'success',
              this.translate.instant('model_detail.notify.stale_removed'),
            );
            this.router.navigate(['/models']);
            return;
          }
          let resolvedRes = res;
          if (!res.new.base_model && !this.meta()?.base_model) {
            const detectedBaseModel = this.detect(this.modelBasename).baseModel;
            if (detectedBaseModel) {
              resolvedRes = { ...res, new: { ...res.new, base_model: detectedBaseModel } };
            }
          }
          this.refetchPreviewData.set(resolvedRes);
          if (res.no_changes) {
            this.refetchNoChanges.set(true);
          } else {
            this.showRefetchModal.set(true);
          }
        },
        error: (err) => {
          this.refetching.set(false);
          this.error.set((err as Error).message);
          this.notifService.show('error', (err as Error).message);
        },
      });
  }

  onModalApplied(meta: ModelMeta) {
    this.showRefetchModal.set(false);
    this.meta.set(meta);
    this.syncEditMeta(meta);
    this.notifService.show('success', this.translate.instant('model_detail.notify.updated'));
    this.loadRepoFiles();
  }

  onModalCancelled() {
    this.showRefetchModal.set(false);
  }

  reviewAnyway() {
    this.refetchNoChanges.set(false);
    this.showRefetchModal.set(true);
  }

  private saveSiblingBaseModels() {
    const edits = this.fileBaseModels();
    for (const f of this.repoFiles()) {
      if (!f.is_downloaded) continue;
      const newVal = edits[f.filename];
      if (newVal === undefined || newVal === f.base_model) continue;
      const path = f.installed_path || f.filename;
      if (path === this.modelPath) continue; // current file is saved by the main save()
      this.modelService
        .updateMetadata(f.model_type, path, { base_model: newVal })
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe();
    }
  }

  addToWorkflow() {
    this.workflowService
      .addToWorkflow(this.modelType, this.modelPath)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () =>
          this.notifService.show('success', this.translate.instant('model_detail.notify.queued')),
        error: () =>
          this.notifService.show(
            'error',
            this.translate.instant('model_detail.notify.queue_failed'),
          ),
      });
  }

  uninstall() {
    this.deleting.set(true);
    this.modelService
      .deleteModel(this.modelType, this.modelPath)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.notifService.show(
            'success',
            this.translate.instant('model_detail.notify.uninstalled', {
              name: this.modelBasename,
            }),
          );
          this.router.navigate(['/models']);
        },
        error: (err) => {
          this.deleting.set(false);
          this.notifService.show('error', (err as Error).message);
        },
      });
  }

  linkSource() {
    const url = this.linkSourceUrl().trim();
    if (!url) return;
    this.linking.set(true);
    this.linkSourceError.set('');
    this.modelService
      .linkSource(this.modelType, this.modelPath, url)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.linking.set(false);
          this.notifService.show(
            'success',
            this.translate.instant('model_detail.notify.source_linked'),
          );
          this.router.navigate(['/models']);
        },
        error: (err) => {
          this.linking.set(false);
          this.linkSourceError.set((err as Error).message);
        },
      });
  }

  addFileToWorkflow(file: RepoFile) {
    const path = file.installed_path || file.filename;
    this.workflowService
      .addToWorkflow(this.modelType, path)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () =>
          this.notifService.show(
            'success',
            this.translate.instant('model_detail.notify.queued_short'),
          ),
        error: () =>
          this.notifService.show(
            'error',
            this.translate.instant('model_detail.notify.queue_failed_short'),
          ),
      });
  }

  deleteFile(file: RepoFile) {
    const path = file.installed_path || file.filename;
    this.modelService
      .deleteModel(this.modelType, path)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.notifService.show(
            'success',
            this.translate.instant('model_detail.notify.file_deleted', {
              filename: file.filename,
            }),
          );
          this.loadRepoFiles();
        },
        error: (err) => this.notifService.show('error', (err as Error).message),
      });
  }

  downloadFile(file: RepoFile) {
    if (!file.download_url || this.downloadingFiles().has(file.filename)) return;
    const dir = this.modelPath.includes('/')
      ? this.modelPath.split('/').slice(0, -1).join('/') + '/'
      : '';
    const destFilename = dir + file.filename;
    const platform = this.meta()?.source_platform ?? '';
    let sourceId = '';
    if (platform === 'civitai') {
      const m = /\/api\/download\/models\/(\d+)/.exec(file.download_url);
      sourceId = m?.[1] ?? '';
    } else if (platform === 'huggingface') {
      sourceId = this.catalogEntry()?.source_page_id ?? '';
    }
    const baseModel = this.detect(file.filename).baseModel;
    this.downloadingFiles.update((s) => new Set(s).add(file.filename));
    this.downloadService
      .startDownload(file.download_url, this.modelType, destFilename, platform, sourceId, baseModel)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.notifService.show(
            'success',
            this.translate.instant('model_detail.notify.downloading', {
              filename: file.filename,
            }),
          );
        },
        error: () => {
          this.downloadingFiles.update((s) => {
            const next = new Set(s);
            next.delete(file.filename);
            return next;
          });
          this.notifService.show(
            'error',
            this.translate.instant('model_detail.notify.download_failed', {
              filename: file.filename,
            }),
          );
        },
      });
  }

  async copyTriggerWords() {
    const text = (this.meta()?.trigger_words ?? []).join(', ');
    try {
      await navigator.clipboard.writeText(text);
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 1400);
      this.notifService.show(
        'success',
        this.translate.instant('model_detail.notify.trigger_copied'),
      );
    } catch {
      this.notifService.show(
        'error',
        this.translate.instant('model_detail.notify.trigger_copy_failed'),
      );
    }
  }

  uploadImages(files: File[]) {
    if (!files.length) return;
    this.uploadBusy.set(true);
    this.uploadError.set('');
    this.modelService
      .uploadModelMedia(this.modelType, this.modelPath, files)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (media) => {
          const current = this.meta();
          if (current) this.meta.set({ ...current, media });
          this.uploadBusy.set(false);
        },
        error: () => {
          this.uploadError.set(this.translate.instant('media_gallery.upload_failed'));
          this.uploadBusy.set(false);
        },
      });
  }

  removeImage(item: GalleryMedia) {
    this.modelService
      .deleteModelMedia(this.modelType, this.modelPath, item.mediaId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (media) => {
          const current = this.meta();
          if (current) this.meta.set({ ...current, media });
        },
        error: () => {
          this.uploadError.set(this.translate.instant('media_gallery.upload_failed'));
        },
      });
  }

  formatBytes = formatBytes;
}
