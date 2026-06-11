import { Component, signal, inject, computed, DestroyRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { toSignal, takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { catchError, of } from 'rxjs';
import { DownloadService, DownloadTask } from '../../services/download';
import { ConfirmPopover } from '../../components/confirm-popover/confirm-popover';

/**
 * The "Active Downloads" queue shown at the top of the Active tab. Self-contained: it
 * reads live tasks from the download service, caps the visible list, and owns the cancel
 * (single / all) flow. Renders nothing when there is nothing in flight.
 */
@Component({
  selector: 'app-download-queue',
  imports: [CommonModule, ConfirmPopover],
  templateUrl: './download-queue.html',
  styleUrl: './download-queue.scss',
})
export class DownloadQueue {
  private readonly dlService = inject(DownloadService);
  private readonly destroyRef = inject(DestroyRef);

  readonly activeTasks = toSignal(this.dlService.activeTasks$, {
    initialValue: [] as DownloadTask[],
  });
  readonly cancelledIds = signal(new Set<string>());
  readonly cancellingIds = signal(new Set<string>());
  readonly displayTasks = computed(() => {
    const all = this.activeTasks().filter((t) => !this.cancelledIds().has(t.id));
    const active = all.filter((t) => t.status === 'queued' || t.status === 'downloading');
    const terminal = all.filter((t) => t.status === 'done' || t.status === 'error');
    const remaining = Math.max(0, 5 - active.length);
    return [...active, ...terminal.slice(0, remaining)];
  });
  readonly hasCancellableTasks = computed(() =>
    this.displayTasks().some((t) => t.status === 'queued' || t.status === 'downloading'),
  );

  onCancelTask(taskId: string): void {
    this.cancellingIds.update((s) => new Set([...s, taskId]));
    this.dlService
      .cancelDownload(taskId)
      .pipe(
        catchError(() => of(void 0)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.cancelledIds.update((s) => new Set([...s, taskId]));
        this.cancellingIds.update((s) => {
          const next = new Set(s);
          next.delete(taskId);
          return next;
        });
      });
  }

  onCancelAll(): void {
    this.displayTasks().forEach((t) => this.onCancelTask(t.id));
  }

  activePct(t: DownloadTask): string {
    return t.progress.toFixed(0) + '%';
  }
}
