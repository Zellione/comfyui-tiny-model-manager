import { ChangeDetectionStrategy, Component, input, output, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

/** Mirrors the four signatures the backend sniffs in `py/services/media_upload.py`. */
export const ACCEPTED_TYPES: readonly string[] = [
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/gif',
];
export const MAX_FILE_BYTES = 10 * 1024 * 1024;
export const MAX_FILES = 10;

/**
 * Drop target and file picker for user-supplied card images.
 *
 * Presentational only: it validates locally for immediate feedback and emits the files.
 * The server re-validates everything — it sniffs magic bytes rather than trusting the
 * browser's `type` — so this check is a convenience, never the guard.
 */
@Component({
  selector: 'app-media-upload-zone',
  imports: [TranslatePipe],
  templateUrl: './media-upload-zone.html',
  styleUrl: './media-upload-zone.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MediaUploadZone {
  /** Set while an upload is in flight; blocks further selections. */
  busy = input(false);
  /** Server-side error message from the parent, rendered under the zone. */
  error = input('');

  readonly filesSelected = output<File[]>();

  readonly dragging = signal(false);
  /** Translation key for the last client-side rejection, or '' when there is none. */
  readonly localError = signal('');

  readonly acceptAttr = ACCEPTED_TYPES.join(',');

  accept(files: File[]) {
    if (this.busy()) return;
    if (!files.length) return;
    if (files.length > MAX_FILES) {
      this.localError.set('media_gallery.upload_error_count');
      return;
    }
    if (files.some((f) => !ACCEPTED_TYPES.includes(f.type))) {
      this.localError.set('media_gallery.upload_error_type');
      return;
    }
    if (files.some((f) => f.size > MAX_FILE_BYTES)) {
      this.localError.set('media_gallery.upload_error_size');
      return;
    }
    this.localError.set('');
    this.filesSelected.emit(files);
  }

  onPicked(event: Event) {
    const input = event.target as HTMLInputElement;
    this.accept(Array.from(input.files ?? []));
    // Clear so picking the same file twice in a row still fires a change event.
    input.value = '';
  }

  onDragOver(event: DragEvent) {
    event.preventDefault();
    this.dragging.set(true);
  }

  onDragLeave() {
    this.dragging.set(false);
  }

  onDrop(event: DragEvent) {
    event.preventDefault();
    this.dragging.set(false);
    this.accept(Array.from(event.dataTransfer?.files ?? []));
  }
}
