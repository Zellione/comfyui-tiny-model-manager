import { Component, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { toSignal } from '@angular/core/rxjs-interop';
import { DownloadService, DownloadTask, CivitaiModel, CivitaiVersion, CivitaiFile, HfModel } from '../../services/download';

type Platform = 'civitai' | 'huggingface';
type ModelType = 'checkpoints' | 'loras' | 'embeddings' | 'vae' | 'controlnet';

@Component({
  selector: 'app-download',
  imports: [CommonModule, FormsModule],
  templateUrl: './download.html',
  styleUrl: './download.scss',
})
export class Download {
  private dlService = inject(DownloadService);

  platform = signal<Platform>('civitai');
  query = signal('');
  modelType = signal<ModelType>('checkpoints');
  modelTypes: ModelType[] = ['checkpoints', 'loras', 'embeddings', 'vae', 'controlnet'];

  civitaiResults = signal<CivitaiModel[]>([]);
  hfResults = signal<HfModel[]>([]);
  activeTasks = toSignal(this.dlService.activeTasks$, { initialValue: [] as DownloadTask[] });

  selectedModel = signal<CivitaiModel | null>(null);
  versions = signal<CivitaiVersion[]>([]);
  hfFiles = signal<{ filename: string; size: number; url: string }[]>([]);
  selectedHfRepoId = signal('');

  searching = signal(false);
  loadingVersions = signal(false);
  versionsError = signal('');

  search() {
    this.searching.set(true);
    this.civitaiResults.set([]);
    this.hfResults.set([]);
    if (this.platform() === 'civitai') {
      this.dlService.searchCivitai(this.query(), this.modelType()).subscribe({
        next: r => { this.civitaiResults.set(r.items); this.searching.set(false); },
        error: () => { this.searching.set(false); },
      });
    } else {
      this.dlService.searchHuggingFace(this.query(), this.modelType()).subscribe({
        next: r => { this.hfResults.set(r); this.searching.set(false); },
        error: () => { this.searching.set(false); },
      });
    }
  }

  selectCivitai(model: CivitaiModel) {
    this.selectedModel.set(model);
    this.versions.set([]);
    this.versionsError.set('');
    this.loadingVersions.set(true);
    this.dlService.getCivitaiVersions(model.id).subscribe({
      next: v => { this.versions.set(v); this.loadingVersions.set(false); },
      error: err => {
        this.versionsError.set(err?.error?.error ?? 'Failed to load versions');
        this.loadingVersions.set(false);
      },
    });
  }

  downloadFile(file: CivitaiFile, versionId: number) {
    this.dlService.startDownload(
      file.downloadUrl,
      this.modelType(),
      file.name,
      'civitai',
      String(versionId)
    ).subscribe();
  }

  selectHf(model: HfModel) {
    const repoId = model.modelId ?? model.id;
    this.selectedHfRepoId.set(repoId);
    this.hfFiles.set([]);
    this.dlService.getHfFiles(repoId).subscribe({
      next: files => this.hfFiles.set(files),
    });
  }

  downloadHf(file: { filename: string; size: number; url: string }) {
    this.dlService.startDownload(file.url, this.modelType(), file.filename, 'huggingface', this.selectedHfRepoId()).subscribe();
  }

  formatSize(bytes: number): string {
    if (bytes >= 1e9) return (bytes / 1e9).toFixed(1) + ' GB';
    if (bytes >= 1e6) return (bytes / 1e6).toFixed(1) + ' MB';
    return (bytes / 1e3).toFixed(0) + ' KB';
  }

  activePct(t: DownloadTask): string {
    return t.progress.toFixed(0) + '%';
  }
}
