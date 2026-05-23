import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DownloadService, DownloadTask, CivitaiModel, CivitaiVersion, HfModel } from '../../services/download';

type Platform = 'civitai' | 'huggingface';
type ModelType = 'checkpoints' | 'loras' | 'embeddings' | 'vae' | 'controlnet';

@Component({
  selector: 'app-download',
  imports: [CommonModule, FormsModule],
  templateUrl: './download.html',
  styleUrl: './download.scss',
})
export class Download implements OnInit {
  platform: Platform = 'civitai';
  query = '';
  modelType: ModelType = 'checkpoints';
  modelTypes: ModelType[] = ['checkpoints', 'loras', 'embeddings', 'vae', 'controlnet'];

  civitaiResults: CivitaiModel[] = [];
  hfResults: HfModel[] = [];
  activeTasks: DownloadTask[] = [];

  selectedModel: CivitaiModel | null = null;
  versions: CivitaiVersion[] = [];
  hfFiles: { filename: string; size: number; url: string }[] = [];

  searching = false;
  loadingVersions = false;

  constructor(private dlService: DownloadService) {}

  ngOnInit() {
    this.dlService.activeTasks$.subscribe(tasks => (this.activeTasks = tasks));
  }

  search() {
    this.searching = true;
    this.civitaiResults = [];
    this.hfResults = [];
    if (this.platform === 'civitai') {
      this.dlService.searchCivitai(this.query, this.modelType).subscribe({
        next: r => { this.civitaiResults = r.items; this.searching = false; },
        error: () => { this.searching = false; },
      });
    } else {
      this.dlService.searchHuggingFace(this.query, this.modelType).subscribe({
        next: r => { this.hfResults = r; this.searching = false; },
        error: () => { this.searching = false; },
      });
    }
  }

  selectCivitai(model: CivitaiModel) {
    this.selectedModel = model;
    this.versions = [];
    this.loadingVersions = true;
    this.dlService.getCivitaiVersions(model.id).subscribe({
      next: v => { this.versions = v; this.loadingVersions = false; },
      error: () => { this.loadingVersions = false; },
    });
  }

  downloadCivitai(version: CivitaiVersion) {
    const file = version.files[0];
    if (!file) return;
    this.dlService.startDownload(
      file.downloadUrl,
      this.modelType,
      file.name,
      'civitai',
      String(this.selectedModel!.id)
    ).subscribe();
  }

  selectHf(model: HfModel) {
    this.hfFiles = [];
    this.dlService.getHfFiles(model.modelId ?? model.id).subscribe({
      next: files => (this.hfFiles = files),
    });
  }

  downloadHf(file: { filename: string; size: number; url: string }, repoId: string) {
    this.dlService.startDownload(file.url, this.modelType, file.filename, 'huggingface', repoId).subscribe();
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
