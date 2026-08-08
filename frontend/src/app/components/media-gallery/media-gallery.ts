import { Component, HostListener, computed, input, linkedSignal, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TranslatePipe } from '@ngx-translate/core';
import { MediaItem } from '../../services/model';
import { isVideo, mediaUrl } from '../../utils/media';
import {
  hideOnError,
  showOnLoad,
  showPosterOnLoad,
  videoPosterUrl as buildVideoPosterUrl,
} from '../../utils/media-events';

/** A gallery entry, normalised from either a local MediaItem or a remote URL. */
export interface GalleryMedia {
  src: string;
  isVideo: boolean;
  /** Poster image for videos; null when none can be derived (remote URLs). */
  poster: string | null;
}

/**
 * Shared media gallery: a large main preview, a thumbnail strip, and an image
 * lightbox. It is the single gallery implementation in the app — model-detail and
 * catalog-detail feed it locally-stored `media`, while download-search and
 * workflows-browse feed it remote `urls`; all four previously carried their own
 * near-duplicate markup, state and styling.
 *
 * The host element is `display: block`; pages set their own padding and width
 * constraints on the `app-media-gallery` element.
 */
@Component({
  selector: 'app-media-gallery',
  imports: [CommonModule, TranslatePipe],
  templateUrl: './media-gallery.html',
  styleUrl: './media-gallery.scss',
})
export class MediaGallery {
  /** Locally-stored media records (model-detail, catalog-detail). */
  media = input<MediaItem[]>([]);
  /** Remote preview URLs (download-search, workflows-browse). */
  urls = input<string[]>([]);

  /**
   * The two inputs are alternative sources for the same gallery, normalised here
   * so the template never has to know which one a page supplied. `media` wins
   * when both are set.
   */
  readonly items = computed<GalleryMedia[]>(() => {
    const local = this.media();
    if (local.length) {
      return local.map((m) => ({
        src: mediaUrl(m.local_path),
        isVideo: m.media_type === 'video',
        poster: m.media_type === 'video' ? buildVideoPosterUrl(m.local_path) : null,
      }));
    }
    return this.urls().map((url) => ({
      src: url,
      isVideo: isVideo(url),
      // Remote videos have no poster route — the ▶ fallback stands alone.
      poster: null,
    }));
  });

  /**
   * Content identity of the current list. Keying the index reset on a string
   * rather than the array keeps it stable across recomputes, so a parent binding
   * a fresh literal (e.g. `[media]="[]"`) does not churn on every check.
   */
  private readonly identity = computed(() =>
    this.items()
      .map((i) => i.src)
      .join('|'),
  );

  /** Resets to the first item whenever the gallery is pointed at different media. */
  readonly galleryIdx = linkedSignal<string, number>({
    source: this.identity,
    computation: () => 0,
  });

  readonly lightboxOpen = signal(false);

  readonly activeMedia = computed(() => {
    const items = this.items();
    if (!items.length) return null;
    return items[Math.min(this.galleryIdx(), items.length - 1)];
  });

  mediaUrl = mediaUrl;

  videoPosterUrl(localPath: string): string {
    return buildVideoPosterUrl(localPath);
  }

  onImgLoad(event: Event) {
    showOnLoad(event);
  }

  onImgError(event: Event) {
    hideOnError(event);
  }

  onVideoPosterLoad(event: Event) {
    showPosterOnLoad(event);
  }

  @HostListener('document:keydown.escape')
  onEscape() {
    if (this.lightboxOpen()) this.lightboxOpen.set(false);
  }
}
