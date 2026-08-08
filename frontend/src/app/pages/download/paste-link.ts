import { Component, signal, inject, computed, DestroyRef } from '@angular/core';
import { hideOnError } from '../../utils/media-events';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, debounceTime, distinctUntilChanged, switchMap, of, catchError, map } from 'rxjs';
import {
  CivitaiService,
  CivitaiVersion,
  CivitaiFile,
  CivitaiDirectLinkInfo,
} from '../../services/civitai';
import { HuggingFaceService } from '../../services/huggingface';
import { detectLink, LinkKind } from '../../utils/link-detector';
import { ModelType } from '../../utils/model-types';
import { formatSize } from '../../utils/format';
import { ModelTypeSelect } from '../../components/model-type-select/model-type-select';
import { BaseModelSelect } from '../../components/base-model-select/base-model-select';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { InstalledFilesService } from '../../services/installed-files';

type HfFileItem = { filename: string; size: number; url: string };

type LinkResolution =
  | { tag: 'hf-resolve'; image_urls?: string[]; filename: string }
  | (CivitaiDirectLinkInfo & { tag: 'civitai-download' })
  | { tag: 'hf-repo'; files: HfFileItem[] }
  | { tag: 'civitai-model'; versions: CivitaiVersion[]; model_type?: string };

/**
 * The "Paste a link" section. Resolves a HuggingFace or CivitAI URL into a
 * downloadable file (or list of files/versions) and enqueues the chosen ones.
 * The installed-file status, filename detection, download enqueue, and per-row
 * override helpers are shared with the search section via InstalledFilesService.
 */
@Component({
  selector: 'app-paste-link',
  imports: [CommonModule, FormsModule, ModelTypeSelect, BaseModelSelect, TranslatePipe],
  templateUrl: './paste-link.html',
  styleUrl: './paste-link.scss',
})
export class PasteLink {
  private readonly civitaiService = inject(CivitaiService);
  private readonly hfService = inject(HuggingFaceService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly installed = inject(InstalledFilesService);
  private readonly translate = inject(TranslateService);
  private readonly pasteUrl$ = new Subject<string>();

  formatSize = formatSize;

  // Per-file type / base-model overrides, keyed by filename or `${versionId}_${fileId}`.
  linkHfRowTypes = signal<Record<string, ModelType>>({});
  linkCivitaiFileTypes = signal<Record<string, ModelType>>({});
  linkHfRowBaseModels = signal<Record<string, string>>({});
  linkCivitaiFileBaseModels = signal<Record<string, string>>({});

  pasteUrl = signal('');
  linkKind = signal<LinkKind>({ type: 'empty' });
  linkModelType = signal<ModelType>('checkpoints');
  linkResolving = signal(false);
  linkError = signal('');
  linkResolved = signal<CivitaiDirectLinkInfo | null>(null);
  linkImages = signal<string[]>([]);
  linkBaseModel = signal('');
  linkHfFiles = signal<HfFileItem[]>([]);
  linkVersions = signal<CivitaiVersion[]>([]);
  linkVersionsError = signal('');
  linkCivitaiSelected = signal(new Map<string, { file: CivitaiFile; versionId: number }>());
  linkCivitaiSelectedCount = computed(() => this.linkCivitaiSelected().size);

  hfResolveKind = computed(() => {
    const k = this.linkKind();
    return k.type === 'hf-resolve' ? k : null;
  });
  civitaiDownloadKind = computed(() => {
    const k = this.linkKind();
    return k.type === 'civitai-download' ? k : null;
  });
  hfRepoKind = computed(() => {
    const k = this.linkKind();
    return k.type === 'hf-repo' ? k : null;
  });
  civitaiModelKind = computed(() => {
    const k = this.linkKind();
    return k.type === 'civitai-model' ? k : null;
  });
  linkFilename = computed(() => {
    const k = this.linkKind();
    if (k.type === 'hf-resolve') return k.filename;
    if (k.type === 'civitai-download') return this.linkResolved()?.filename ?? '';
    return '';
  });
  canSubmitLink = computed(() => {
    const k = this.linkKind();
    if (k.type === 'hf-resolve') return true;
    if (k.type === 'civitai-download') return !!this.linkResolved() && !this.linkResolving();
    return false;
  });

  constructor() {
    this.pasteUrl$
      .pipe(
        debounceTime(300),
        distinctUntilChanged(),
        switchMap((url) => {
          const kind = detectLink(url);
          this.linkKind.set(kind);
          this.linkResolved.set(null);
          this.linkImages.set([]);
          this.linkError.set('');
          this.linkHfFiles.set([]);
          this.linkVersions.set([]);
          this.linkVersionsError.set('');
          this.linkCivitaiSelected.set(new Map());
          this.linkCivitaiFileTypes.set({});
          this.linkBaseModel.set('');
          this.linkHfRowBaseModels.set({});
          this.linkCivitaiFileBaseModels.set({});
          if (kind.type === 'hf-resolve') {
            this.linkResolving.set(true);
            return this.hfService.resolveDirectLink(kind.repo).pipe(
              map((r) => ({
                tag: 'hf-resolve' as const,
                image_urls: r.image_urls,
                filename: kind.filename,
              })),
              catchError(() =>
                of({
                  tag: 'hf-resolve' as const,
                  image_urls: [] as string[],
                  filename: kind.filename,
                }),
              ),
            );
          }
          if (kind.type === 'civitai-download') {
            this.linkResolving.set(true);
            return this.civitaiService.resolveDirectLink(kind.versionId).pipe(
              map((r) => ({ tag: 'civitai-download' as const, ...r })),
              catchError((err) => {
                this.linkError.set(
                  err?.error?.error ?? this.translate.instant('paste_link.error.resolve_failed'),
                );
                this.linkResolving.set(false);
                return of(null);
              }),
            );
          }
          if (kind.type === 'hf-repo') {
            this.linkResolving.set(true);
            return this.hfService.getFiles(kind.repo).pipe(
              map((files) => ({ tag: 'hf-repo' as const, files })),
              catchError(() => {
                this.linkError.set(this.translate.instant('paste_link.error.load_files_failed'));
                this.linkResolving.set(false);
                return of(null);
              }),
            );
          }
          if (kind.type === 'civitai-model') {
            this.linkResolving.set(true);
            return this.civitaiService.getVersions(kind.modelId).pipe(
              map((r) => ({
                tag: 'civitai-model' as const,
                versions: r.versions,
                model_type: r.model_type,
              })),
              catchError((err) => {
                this.linkVersionsError.set(
                  err?.error?.error ??
                    this.translate.instant('paste_link.error.load_versions_failed'),
                );
                this.linkResolving.set(false);
                return of(null);
              }),
            );
          }
          return of(null);
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((result) => this.applyLinkResolution(result));
  }

  fileStatus(filename: string) {
    return this.installed.fileStatus(filename);
  }

  linkHfRowType(name: string): ModelType {
    return this.installed.readOverride(this.linkHfRowTypes, name, 'checkpoints');
  }
  setLinkHfRowType(name: string, t: ModelType) {
    this.installed.writeOverride(this.linkHfRowTypes, name, t);
  }
  linkCivitaiFileType(versionId: number, file: CivitaiFile): ModelType {
    return this.installed.readOverride(
      this.linkCivitaiFileTypes,
      this.installed.fileKey(versionId, file),
      'checkpoints',
    );
  }
  setLinkCivitaiFileType(versionId: number, file: CivitaiFile, t: ModelType) {
    this.installed.writeOverride(
      this.linkCivitaiFileTypes,
      this.installed.fileKey(versionId, file),
      t,
    );
  }
  linkHfRowBaseModel(name: string): string {
    return this.installed.readOverride(this.linkHfRowBaseModels, name, '');
  }
  setLinkHfRowBaseModel(name: string, v: string) {
    this.installed.writeOverride(this.linkHfRowBaseModels, name, v);
  }
  linkCivitaiFileBaseModel(versionId: number, file: CivitaiFile): string {
    return this.installed.readOverride(
      this.linkCivitaiFileBaseModels,
      this.installed.fileKey(versionId, file),
      '',
    );
  }
  setLinkCivitaiFileBaseModel(versionId: number, file: CivitaiFile, v: string) {
    this.installed.writeOverride(
      this.linkCivitaiFileBaseModels,
      this.installed.fileKey(versionId, file),
      v,
    );
  }

  private applyHfResolve(result: {
    tag: 'hf-resolve';
    image_urls?: string[];
    filename: string;
  }): void {
    this.linkImages.set(result.image_urls ?? []);
    const det = this.installed.detect(result.filename);
    if (det.modelType) this.linkModelType.set(det.modelType);
    this.linkBaseModel.set(det.baseModel);
  }

  private applyCivitaiDownload(result: CivitaiDirectLinkInfo & { tag: 'civitai-download' }): void {
    this.linkResolved.set(result);
    this.linkModelType.set((result.model_type as ModelType) ?? 'checkpoints');
    this.linkImages.set(result.image_urls ?? []);
    this.linkBaseModel.set(this.installed.detect(result.filename).baseModel);
  }

  private applyHfRepo(result: { tag: 'hf-repo'; files: HfFileItem[] }): void {
    this.linkHfFiles.set(result.files);
    const types: Record<string, ModelType> = {};
    const baseModels: Record<string, string> = {};
    for (const f of result.files) {
      const det = this.installed.detect(f.filename);
      if (det.modelType) types[f.filename] = det.modelType;
      if (det.baseModel) baseModels[f.filename] = det.baseModel;
    }
    this.linkHfRowTypes.set(types);
    this.linkHfRowBaseModels.set(baseModels);
  }

  private applyCivitaiModel(result: {
    tag: 'civitai-model';
    versions: CivitaiVersion[];
    model_type?: string;
  }): void {
    this.linkVersions.set(result.versions);
    const detectedType = (result.model_type as ModelType) ?? 'checkpoints';
    this.linkModelType.set(detectedType);
    const types: Record<string, ModelType> = {};
    const baseModels: Record<string, string> = {};
    for (const v of result.versions) {
      for (const f of v.files) {
        const key = `${v.id}_${f.id}`;
        types[key] = detectedType;
        baseModels[key] = v.baseModel || this.installed.detect(f.name).baseModel;
      }
    }
    this.linkCivitaiFileTypes.set(types);
    this.linkCivitaiFileBaseModels.set(baseModels);
    const selection = new Map<string, { file: CivitaiFile; versionId: number }>();
    for (const v of result.versions) {
      for (const f of v.files) {
        if (f.primary) {
          selection.set(`${v.id}_${f.id}`, { file: f, versionId: v.id });
        }
      }
    }
    this.linkCivitaiSelected.set(selection);
  }

  private applyLinkResolution(result: LinkResolution | null): void {
    if (result) {
      if (result.tag === 'hf-resolve') this.applyHfResolve(result);
      else if (result.tag === 'civitai-download') this.applyCivitaiDownload(result);
      else if (result.tag === 'hf-repo') this.applyHfRepo(result);
      else if (result.tag === 'civitai-model') this.applyCivitaiModel(result);
    }
    this.linkResolving.set(false);
  }

  onPasteUrlChange(url: string) {
    this.pasteUrl.set(url);
    this.pasteUrl$.next(url);
  }

  submitDirectLink() {
    const kind = this.linkKind();
    const type = this.linkModelType();
    const baseModel = this.linkBaseModel();
    if (kind.type === 'hf-resolve') {
      // `downloadUrl`, not the pasted URL: a `/blob/` link serves the HTML file viewer.
      this.installed.enqueue(
        kind.downloadUrl,
        type,
        kind.filename,
        'huggingface',
        kind.repo,
        baseModel,
      );
    } else if (kind.type === 'civitai-download') {
      const r = this.linkResolved();
      if (!r) return;
      this.installed.enqueue(
        this.pasteUrl(),
        type,
        r.filename,
        'civitai',
        String(kind.versionId),
        baseModel,
      );
    }
    this.pasteUrl.set('');
    this.linkKind.set({ type: 'empty' });
    this.linkResolved.set(null);
    this.linkImages.set([]);
    this.linkError.set('');
    this.linkBaseModel.set('');
  }

  // F-19 — HF repo link method
  downloadLinkHfFile(f: HfFileItem) {
    const kind = this.linkKind();
    const repo = kind.type === 'hf-repo' ? kind.repo : '';
    this.installed.enqueue(
      f.url,
      this.linkHfRowType(f.filename),
      f.filename,
      'huggingface',
      repo,
      this.linkHfRowBaseModel(f.filename),
    );
  }

  // F-20 — CivitAI model link methods
  toggleLinkCivitaiFile(versionId: number, file: CivitaiFile) {
    const key = `${versionId}_${file.id}`;
    this.linkCivitaiSelected.update((prev) => {
      const next = new Map(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.set(key, { file, versionId });
      }
      return next;
    });
  }

  isLinkCivitaiFileSelected(versionId: number, file: CivitaiFile): boolean {
    return this.linkCivitaiSelected().has(`${versionId}_${file.id}`);
  }

  downloadLinkFile(file: CivitaiFile, versionId: number) {
    this.installed.enqueue(
      file.downloadUrl,
      this.linkCivitaiFileType(versionId, file),
      file.name,
      'civitai',
      String(versionId),
      this.linkCivitaiFileBaseModel(versionId, file),
    );
  }

  downloadSelectedLinkCivitai() {
    for (const { file, versionId } of this.linkCivitaiSelected().values()) {
      this.installed.enqueue(
        file.downloadUrl,
        this.linkCivitaiFileType(versionId, file),
        file.name,
        'civitai',
        String(versionId),
        this.linkCivitaiFileBaseModel(versionId, file),
      );
    }
    this.linkCivitaiSelected.set(new Map());
  }

  onImgError(event: Event) {
    hideOnError(event);
  }
}
