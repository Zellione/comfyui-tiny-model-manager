import { Component, OnInit } from '@angular/core';
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
  modelsByType: Record<string, ModelFile[]> = {};
  typeKeys: string[] = [];
  loading = true;
  error = '';

  constructor(private modelService: ModelService) {}

  ngOnInit() {
    this.load();
  }

  load() {
    this.loading = true;
    this.modelService.listModels().subscribe({
      next: data => {
        this.modelsByType = data;
        this.typeKeys = Object.keys(data);
        this.loading = false;
      },
      error: err => {
        this.error = err.message;
        this.loading = false;
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
      error: err => alert('Delete failed: ' + err.message),
    });
  }
}
