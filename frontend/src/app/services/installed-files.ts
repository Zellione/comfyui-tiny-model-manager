import { Injectable, signal, inject, DestroyRef, WritableSignal } from '@angular/core';
import { toSignal, toObservable, takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DownloadService, DownloadTask } from './download';
import { ModelService } from './model';
import { NotificationService } from './notification';
import { KeywordsService } from './keywords';
import { ModelType } from '../utils/model-types';
import { detectFromFilename, FilenameKeyword } from '../utils/filename-detector';
import { CivitaiFile } from './civitai';

/**
 * Shared download/install concern for the download page. The search results and
 * the paste-a-link sections both need to know which files are already installed
 * or downloading, run filename detection, enqueue downloads, and read/write the
 * per-row type/base-model override maps. Provided at the `Download` component
 * level so all sibling sections share one installed-file set and a single
 * `listModels()` fetch per page visit.
 */
@Injectable()
export class InstalledFilesService {
  private readonly dlService = inject(DownloadService);
  private readonly modelService = inject(ModelService);
  private readonly notifService = inject(NotificationService);
  private readonly keywordsService = inject(KeywordsService);
  private readonly destroyRef = inject(DestroyRef);

  readonly keywords = toSignal(this.keywordsService.getKeywords(), {
    initialValue: [] as FilenameKeyword[],
  });
  readonly activeTasks = toSignal(this.dlService.activeTasks$, {
    initialValue: [] as DownloadTask[],
  });
  readonly installedFilenames = signal(new Set<string>());

  constructor() {
    this.modelService
      .listModels()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((models) => {
        const names = new Set<string>();
        for (const files of Object.values(models)) {
          for (const f of files) names.add(f.filename);
        }
        this.installedFilenames.set(names);
      });

    toObservable(this.activeTasks)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((tasks) => {
        const done = tasks.filter((t) => t.status === 'done').map((t) => t.filename);
        if (done.length > 0) {
          this.installedFilenames.update((prev) => {
            const next = new Set(prev);
            done.forEach((f) => next.add(f));
            return next;
          });
        }
      });
  }

  detect(filename: string) {
    return detectFromFilename(filename, this.keywords());
  }

  fileStatus(filename: string): 'idle' | 'downloading' | 'installed' | 'error' {
    // HuggingFace files may have a subfolder prefix in their listed name (e.g.
    // "split_files/model.safetensors"). The downloader strips this to the basename
    // before saving, so we match on the basename here for correct status resolution.
    const base = filename.split('/').pop() ?? filename;
    const task = this.activeTasks().find((t) => t.filename === base);
    if (task) {
      if (task.status === 'done') return 'installed';
      if (task.status === 'error') return 'error';
      return 'downloading';
    }
    return this.installedFilenames().has(base) ? 'installed' : 'idle';
  }

  /** Start a download and toast on success. Shared by all download buttons. */
  enqueue(
    url: string,
    type: ModelType,
    filename: string,
    platform: string,
    sourceId: string,
    baseModel = '',
  ) {
    this.dlService
      .startDownload(url, type, filename, platform, sourceId, baseModel)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => this.notifService.show('success', `Download enqueued: ${filename}`),
      });
  }

  // All per-row "type"/"base-model" overrides are keyed maps with a default; these
  // helpers carry the read/update logic so each accessor stays a one-line binding.
  readOverride<T>(map: WritableSignal<Record<string, T>>, key: string, fallback: T): T {
    return map()[key] ?? fallback;
  }
  writeOverride<T>(map: WritableSignal<Record<string, T>>, key: string, value: T): void {
    map.update((m) => ({ ...m, [key]: value }));
  }
  fileKey(versionId: number, file: CivitaiFile): string {
    return `${versionId}_${file.id}`;
  }
}
