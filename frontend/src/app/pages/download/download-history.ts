import { Component, signal, inject, computed, DestroyRef, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { toSignal, toObservable, takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { skip, debounceTime, pairwise, catchError, of } from 'rxjs';
import { DownloadService, DownloadTask, DownloadHistoryEntry } from '../../services/download';
import { NotificationService } from '../../services/notification';
import { ConfirmPopover } from '../../components/confirm-popover/confirm-popover';

/**
 * Download-history tab. Rendered only while the History tab is open (the parent guards it
 * with `@if`), so it loads on construction and owns all history state and the live-task
 * overlay. It reports a redownload via `switchToActive` so the parent can re-focus the
 * Active tab.
 */
@Component({
  selector: 'app-download-history',
  imports: [CommonModule, FormsModule, ConfirmPopover],
  templateUrl: './download-history.html',
  styleUrl: './download-history.scss',
})
export class DownloadHistory {
  private readonly dlService = inject(DownloadService);
  private readonly notifService = inject(NotificationService);
  private readonly destroyRef = inject(DestroyRef);

  /** Emitted when a redownload is enqueued so the parent can switch to the Active tab. */
  readonly switchToActive = output<void>();

  private readonly activeTasks = toSignal(this.dlService.activeTasks$, {
    initialValue: [] as DownloadTask[],
  });

  readonly historyEntries = signal<DownloadHistoryEntry[]>([]);
  readonly historyTotal = signal(0);
  readonly historyPage = signal(1);
  readonly historyLoading = signal(false);
  readonly historyLoadMoreError = signal('');
  readonly historyStatusFilter = signal('');
  readonly historySearch = signal('');
  readonly historyHasMore = computed(() => this.historyEntries().length < this.historyTotal());
  readonly historyRedownloadingIds = signal(new Set<number>());
  readonly cancellingIds = signal(new Set<string>());
  readonly historyTaskMap = computed(() => {
    const m = new Map<number, DownloadTask>();
    for (const t of this.activeTasks()) {
      if (t.history_id != null) m.set(t.history_id, t);
    }
    return m;
  });

  constructor() {
    // The component mounts when the History tab opens, so load the first page immediately.
    this.loadHistory(true);

    // Reload from the first page whenever the status filter or search term changes.
    toObservable(computed(() => ({ status: this.historyStatusFilter(), q: this.historySearch() })))
      .pipe(skip(1), debounceTime(300), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.loadHistory(true));

    // Reflect a live download's terminal status onto its matching history row.
    toObservable(this.activeTasks)
      .pipe(pairwise(), takeUntilDestroyed(this.destroyRef))
      .subscribe(([prev, curr]) => {
        for (const task of curr) {
          if (task.history_id == null) continue;
          const prevStatus = prev.find((p) => p.id === task.id)?.status;
          if (prevStatus === task.status) continue;
          if (task.status === 'done' || task.status === 'error' || task.status === 'cancelled') {
            this.historyEntries.update((entries) =>
              entries.map((e) =>
                e.id === task.history_id
                  ? { ...e, status: task.status as DownloadHistoryEntry['status'] }
                  : e,
              ),
            );
          }
        }
      });
  }

  loadHistory(reset = true): void {
    if (reset) {
      this.historyPage.set(1);
      this.historyEntries.set([]);
    }
    this.historyLoading.set(true);
    this.historyLoadMoreError.set('');
    this.dlService
      .getHistory(this.historyStatusFilter(), this.historySearch(), this.historyPage(), 20)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (r) => {
          if (reset) {
            this.historyEntries.set(r.entries);
          } else {
            this.historyEntries.update((prev) => [...prev, ...r.entries]);
          }
          this.historyTotal.set(r.total);
          this.historyLoading.set(false);
        },
        error: () => {
          this.historyLoadMoreError.set('Failed to load history');
          this.historyLoading.set(false);
        },
      });
  }

  historyLoadMore(): void {
    this.historyPage.update((p) => p + 1);
    this.loadHistory(false);
  }

  redownload(entry: DownloadHistoryEntry): void {
    this.historyRedownloadingIds.update((s) => new Set([...s, entry.id]));
    this.dlService
      .redownload(entry.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.historyRedownloadingIds.update((s) => {
            const next = new Set(s);
            next.delete(entry.id);
            return next;
          });
          this.notifService.show('success', `Redownload enqueued: ${entry.model_name}`);
          this.switchToActive.emit();
        },
        error: () => {
          this.historyRedownloadingIds.update((s) => {
            const next = new Set(s);
            next.delete(entry.id);
            return next;
          });
          this.notifService.show('error', `Failed to redownload: ${entry.model_name}`);
        },
      });
  }

  onCancelTask(taskId: string): void {
    this.cancellingIds.update((s) => new Set([...s, taskId]));
    this.dlService
      .cancelDownload(taskId)
      .pipe(
        catchError(() => of(void 0)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.cancellingIds.update((s) => {
          const next = new Set(s);
          next.delete(taskId);
          return next;
        });
      });
  }

  historyStatusLabel(status: DownloadHistoryEntry['status']): string {
    const map: Record<string, string> = {
      downloading: 'Downloading',
      done: 'Done',
      error: 'Error',
      cancelled: 'Cancelled',
      deleted: 'Deleted',
    };
    return map[status] ?? status;
  }

  canRedownload(status: DownloadHistoryEntry['status']): boolean {
    return status === 'error' || status === 'cancelled' || status === 'deleted';
  }
}
