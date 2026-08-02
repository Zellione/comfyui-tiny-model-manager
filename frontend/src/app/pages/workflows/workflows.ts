import { Component, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { WorkflowsBrowse } from './workflows-browse';
import { WorkflowsInstalled } from './workflows-installed';

/**
 * Workflows page shell (F-129): a toggle between browsing CivitAI's Workflows type and
 * the locally stored workflows. Same shape as the Download page's tab bar; each view
 * keeps the full page height instead of competing for it.
 */
@Component({
  selector: 'app-workflows',
  imports: [WorkflowsBrowse, WorkflowsInstalled, TranslatePipe],
  templateUrl: './workflows.html',
  styleUrl: './workflows.scss',
})
export class Workflows {
  activeTab = signal<'browse' | 'installed'>('browse');
}
