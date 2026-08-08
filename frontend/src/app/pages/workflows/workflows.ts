import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TranslatePipe } from '@ngx-translate/core';
import { WorkflowStoreService } from '../../services/workflow-store';
import { WorkflowsBrowse } from './workflows-browse';
import { WorkflowsInstalled } from './workflows-installed';

/**
 * Workflows page shell (F-129): a toggle between browsing CivitAI's Workflows type and
 * the locally stored workflows. Same shape as the Download page's tab bar; each view
 * keeps the full page height instead of competing for it.
 *
 * The initial tab depends on the store (#156): a user who already has workflows lands on
 * Installed, everyone else on Browse. The count is resolved before either view mounts, so
 * the wrong tab never flashes.
 */
@Component({
  selector: 'app-workflows',
  imports: [WorkflowsBrowse, WorkflowsInstalled, TranslatePipe],
  templateUrl: './workflows.html',
  styleUrl: './workflows.scss',
})
export class Workflows {
  private readonly store = inject(WorkflowStoreService);
  private readonly destroyRef = inject(DestroyRef);

  /** `null` while the installed count is still being resolved — neither view mounts yet. */
  activeTab = signal<'browse' | 'installed' | null>(null);

  constructor() {
    this.store
      .list()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (entries) => this.activeTab.set(entries.length > 0 ? 'installed' : 'browse'),
        // A failing list must not leave the page blank; browse works without the store.
        error: () => this.activeTab.set('browse'),
      });
  }
}
