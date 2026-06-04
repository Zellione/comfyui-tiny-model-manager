const MEDIA_API = '/tiny-model-manager/api/media';

/** Build the URL that serves a locally-stored media file. */
export function mediaUrl(path: string): string {
  return `${MEDIA_API}/${encodeURIComponent(path)}`;
}

/** Heuristic: does this URL point at a video file? */
export function isVideo(url: string): boolean {
  const lower = url.toLowerCase();
  return lower.includes('.mp4') || lower.includes('.webm') || lower.includes('.mov');
}
