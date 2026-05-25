import { Component, OnInit, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import { ModelService, ModelFile, ModelMeta } from '../../services/model';
import { WorkflowService } from '../../services/workflow';

const MEDIA_API = '/tiny-model-manager/api/media';

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
  selected = signal<Set<string>>(new Set());
  queuedForWorkflow = signal<Set<string>>(new Set());

  constructor(private modelService: ModelService, private workflowService: WorkflowService) {}

  ngOnInit() {
    this.load();
  }

  load() {
    this.loading.set(true);
    this.selected.set(new Set());
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

  thumbnailUrl(meta?: ModelMeta): string | null {
    const img = meta?.media?.find(m => m.media_type === 'image');
    return img ? `${MEDIA_API}/${encodeURIComponent(img.local_path)}` : null;
  }

  private selectionKey(type: string, filename: string): string {
    return `${type}::${filename}`;
  }

  isSelected(type: string, filename: string): boolean {
    return this.selected().has(this.selectionKey(type, filename));
  }

  toggleSelect(type: string, filename: string) {
    const key = this.selectionKey(type, filename);
    const s = new Set(this.selected());
    s.has(key) ? s.delete(key) : s.add(key);
    this.selected.set(s);
  }

  selectedForType(type: string): string[] {
    const prefix = `${type}::`;
    return [...this.selected()]
      .filter(k => k.startsWith(prefix))
      .map(k => k.slice(prefix.length));
  }

  deleteModel(type: string, file: ModelFile) {
    if (!confirm(`Delete ${file.filename}?`)) return;
    this.modelService.deleteModel(type, file.filename).subscribe({
      next: () => this.load(),
      error: err => alert('Delete failed: ' + (err as Error).message),
    });
  }

  isQueuedForWorkflow(filename: string): boolean {
    return this.queuedForWorkflow().has(filename);
  }

  addToWorkflow(type: string, filename: string) {
    this.workflowService.addToWorkflow(type, filename).subscribe({
      next: () => {
        const s = new Set(this.queuedForWorkflow());
        s.add(filename);
        this.queuedForWorkflow.set(s);
        setTimeout(() => {
          const s2 = new Set(this.queuedForWorkflow());
          s2.delete(filename);
          this.queuedForWorkflow.set(s2);
        }, 2000);
      },
      error: () => alert('Failed to enqueue model for workflow insertion.'),
    });
  }

  deleteSelected(type: string) {
    const files = this.selectedForType(type);
    if (!files.length) return;
    if (!confirm(`Delete ${files.length} model(s)?`)) return;
    forkJoin(files.map(f => this.modelService.deleteModel(type, f))).subscribe({
      next: () => this.load(),
      error: err => alert('Delete failed: ' + (err as Error).message),
    });
  }
}
