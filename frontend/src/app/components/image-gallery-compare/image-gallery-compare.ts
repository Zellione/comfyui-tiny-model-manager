import { Component, effect, input, model } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TranslatePipe } from '@ngx-translate/core';
import { MediaItem } from '../../services/model';
import { mediaUrl } from '../../utils/media';

@Component({
  selector: 'app-image-gallery-compare',
  imports: [CommonModule, TranslatePipe],
  templateUrl: './image-gallery-compare.html',
  styleUrl: './image-gallery-compare.scss',
})
export class ImageGalleryCompare {
  currentMedia = input<MediaItem[]>([]);
  incomingUrls = input<string[]>([]);
  selectedIncoming = model<string[]>([]);
  keepExisting = model<string[]>([]);

  constructor() {
    effect(() => {
      this.selectedIncoming.set([...this.incomingUrls()]);
      this.keepExisting.set([]);
    });
  }

  mediaUrl = mediaUrl;

  toggleIncoming(url: string) {
    const current = this.selectedIncoming();
    if (current.includes(url)) {
      this.selectedIncoming.set(current.filter((u) => u !== url));
    } else {
      this.selectedIncoming.set([...current, url]);
    }
  }

  toggleExisting(localPath: string) {
    const current = this.keepExisting();
    if (current.includes(localPath)) {
      this.keepExisting.set(current.filter((p) => p !== localPath));
    } else {
      this.keepExisting.set([...current, localPath]);
    }
  }

  isIncomingSelected(url: string): boolean {
    return this.selectedIncoming().includes(url);
  }

  isExistingKept(localPath: string): boolean {
    return this.keepExisting().includes(localPath);
  }
}
