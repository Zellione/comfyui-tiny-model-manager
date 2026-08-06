/**
 * Shared template event handlers for the hidden-until-loaded thumbnail pattern:
 * images start with display:none so the browser's broken-image icon never shows,
 * are revealed on load and stay hidden on error (see mem:conventions).
 */

/** Reveal an image once it has successfully loaded. */
export function showOnLoad(event: Event): void {
  (event.target as HTMLImageElement).style.display = 'block';
}

/** Keep (or make) a failing image hidden. */
export function hideOnError(event: Event): void {
  (event.target as HTMLImageElement).style.display = 'none';
}

/**
 * Reveal a loaded video poster and hide the ▶ fallback that precedes it in the DOM.
 * The ▶ div must come before the img — this relies on previousElementSibling.
 */
export function showPosterOnLoad(event: Event): void {
  const img = event.target as HTMLImageElement;
  img.style.display = 'block';
  const fallback = img.previousElementSibling as HTMLElement | null;
  if (fallback) fallback.style.display = 'none';
}

/** URL of the on-demand poster extraction route for a local video path. */
export function videoPosterUrl(localPath: string): string {
  return `/tiny-model-manager/api/media-poster/${encodeURIComponent(localPath)}`;
}
