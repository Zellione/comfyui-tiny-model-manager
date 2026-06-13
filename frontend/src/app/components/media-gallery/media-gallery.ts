import { Component, HostListener, computed, input, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TranslatePipe } from '@ngx-translate/core';
import { MediaItem } from '../../services/model';
import { mediaUrl } from '../../utils/media';

/**
 * Shared media gallery: a large main preview, a thumbnail strip, and an image
 * lightbox. Used by the model-detail and catalog-detail pages, which previously
 * carried byte-for-byte copies of this markup, state and styling.
 *
 * The host element is `display: block`; pages set their own padding on the
 * `app-media-gallery` element (the only per-page difference).
 */
@Component({
  selector: 'app-media-gallery',
  imports: [CommonModule, TranslatePipe],
  templateUrl: './media-gallery.html',
  styleUrl: './media-gallery.scss',
})
export class MediaGallery {
  media = input<MediaItem[]>([]);

  readonly galleryIdx = signal(0);
  readonly lightboxOpen = signal(false);

  readonly activeMedia = computed(() => {
    const m = this.media();
    if (!m.length) return null;
    return m[Math.min(this.galleryIdx(), m.length - 1)];
  });

  mediaUrl = mediaUrl;

  videoPosterUrl(localPath: string): string {
    return mediaUrl(localPath.replace(/\.[^.]+$/, '') + '_poster.jpg');
  }

  onImgLoad(event: Event) {
    (event.target as HTMLImageElement).style.display = 'block';
  }

  onImgError(event: Event) {
    (event.target as HTMLImageElement).style.display = 'none';
  }

  onVideoPosterLoad(event: Event) {
    const img = event.target as HTMLImageElement;
    img.style.display = 'block';
    const fallback = img.previousElementSibling as HTMLElement | null;
    if (fallback) fallback.style.display = 'none';
  }

  @HostListener('document:keydown.escape')
  onEscape() {
    if (this.lightboxOpen()) this.lightboxOpen.set(false);
  }
}
