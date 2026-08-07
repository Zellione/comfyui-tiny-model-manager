import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { StoredWorkflow, WorkflowEntry, WorkflowStoreService } from '../../services/workflow-store';
import { NotificationService } from '../../services/notification';
import { ConfirmPopover } from '../../components/confirm-popover/confirm-popover';
import { mediaUrl } from '../../utils/media';
import { hideOnError, showOnLoad } from '../../utils/media-events';

/**
 * The locally stored workflows: one card per downloaded CivitAI page, listing every
 * ComfyUI graph its archive contained. Each graph can be loaded onto the open ComfyUI
 * canvas, exported into ComfyUI's own workflow browser, or downloaded as raw JSON.
 */
@Component({
  selector: 'app-workflows-installed',
  imports: [CommonModule, ConfirmPopover, TranslatePipe],
  templateUrl: './workflows-installed.html',
  styleUrl: './workflows-installed.scss',
})
export class WorkflowsInstalled {
  private readonly store = inject(WorkflowStoreService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly notifService = inject(NotificationService);
  private readonly translate = inject(TranslateService);

  entries = signal<WorkflowEntry[]>([]);
  loading = signal(true);
  error = signal('');
  busyWorkflowId = signal<number | null>(null);

  readonly totalGraphs = computed(() => this.entries().reduce((sum, e) => sum + e.items.length, 0));

  constructor() {
    this.load();
  }

  load() {
    this.loading.set(true);
    this.error.set('');
    this.store
      .list()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (entries) => {
          this.entries.set(entries);
          this.loading.set(false);
        },
        error: (err: HttpErrorResponse) => {
          this.error.set(err.error?.error ?? err.message ?? 'Failed to load workflows');
          this.loading.set(false);
        },
      });
  }

  /** Hand the graph to the ComfyUI extension, which loads it onto the canvas. */
  loadInComfy(workflow: StoredWorkflow) {
    this.busyWorkflowId.set(workflow.id);
    this.store
      .openInComfy(workflow.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.busyWorkflowId.set(null);
          this.notifService.show(
            'success',
            this.translate.instant('workflows.notify.queued', { name: workflow.name }),
          );
        },
        error: () => {
          this.busyWorkflowId.set(null);
          this.notifService.show('error', this.translate.instant('workflows.error.open_failed'));
        },
      });
  }

  export(workflow: StoredWorkflow) {
    this.busyWorkflowId.set(workflow.id);
    this.store
      .exportWorkflow(workflow.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.busyWorkflowId.set(null);
          this.notifService.show(
            'success',
            this.translate.instant('workflows.notify.exported', { name: workflow.name }),
          );
        },
        error: () => {
          this.busyWorkflowId.set(null);
          this.notifService.show('error', this.translate.instant('workflows.error.export_failed'));
        },
      });
  }

  deleteEntry(entry: WorkflowEntry) {
    this.store
      .deleteEntry(entry.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.entries.update((list) => list.filter((e) => e.id !== entry.id));
          this.notifService.show(
            'success',
            this.translate.instant('workflows.notify.deleted', { name: entry.display_name }),
          );
        },
        error: () => {
          this.notifService.show('error', this.translate.instant('workflows.error.delete_failed'));
        },
      });
  }

  fileUrl(workflow: StoredWorkflow): string {
    return this.store.fileUrl(workflow.id);
  }

  /** Locally stored preview first; the remote CivitAI URL is the fallback. */
  thumbUrl(entry: WorkflowEntry): string {
    const image = entry.media.find((m) => m.media_type === 'image');
    if (image) return mediaUrl(image.local_path);
    return entry.thumbnail_url ?? '';
  }

  onImgLoad(event: Event) {
    showOnLoad(event);
  }

  onImgError(event: Event) {
    hideOnError(event);
  }
}
