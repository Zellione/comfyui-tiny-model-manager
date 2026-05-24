import { Component, OnInit, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ModelService, ModelFile } from '../../services/model';

@Component({
  selector: 'app-models',
  imports: [CommonModule, RouterLink],
  templateUrl: './models.html',
  styleUrl: './models.scss',
})
export class Models implements OnInit {
  modelsByType = signal<Record<string, ModelFile[]>>({});
  typeKeys = computed(() => Object.keys(this.modelsByType()));
  loading = signal(true);
  error = signal('');

  constructor(private modelService: ModelService) {}

  ngOnInit() {
    this.load();
  }

  load() {
    this.loading.set(true);
    this.modelService.listModels().subscribe({
      next: data => {
        this.modelsByType.set(data);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err.message);
        this.loading.set(false);
      },
    });
  }

  formatSize(bytes: number): string {
    if (bytes >= 1e9) return (bytes / 1e9).toFixed(1) + ' GB';
    if (bytes >= 1e6) return (bytes / 1e6).toFixed(1) + ' MB';
    return (bytes / 1e3).toFixed(0) + ' KB';
  }

  deleteModel(type: string, file: ModelFile) {
    if (!confirm(`Delete ${file.filename}?`)) return;
    this.modelService.deleteModel(type, file.filename).subscribe({
      next: () => this.load(),
      error: err => alert('Delete failed: ' + (err as Error).message),
    });
  }
}
