import { Component, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { InstalledFilesService } from '../../services/installed-files';
import { DownloadHistory } from './download-history';
import { DownloadQueue } from './download-queue';
import { PasteLink } from './paste-link';
import { DownloadSearch } from './download-search';

/**
 * Download page shell: a tab bar over the Active and History tabs. The Active
 * tab composes the queue, paste-a-link, and search sections, which share one
 * InstalledFilesService instance provided here.
 */
@Component({
  selector: 'app-download',
  imports: [DownloadHistory, DownloadQueue, PasteLink, DownloadSearch, TranslatePipe],
  providers: [InstalledFilesService],
  templateUrl: './download.html',
  styleUrl: './download.scss',
})
export class Download {
  activeTab = signal<'active' | 'history'>('active');
}
