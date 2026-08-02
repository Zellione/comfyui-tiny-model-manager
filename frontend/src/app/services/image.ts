import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { StoredWorkflow } from './workflow-store';

/** Which recreation path an image supports, as decided by the backend. */
export type Recreatable = 'graph' | 'params' | '';

/**
 * Generation parameters as CivitAI reports them.
 *
 * Deliberately loose: the API mixes camelCase (`cfgScale`) with capitalised A1111 keys
 * (`Model`, `Model hash`, `Size`) and adds new ones without notice.
 */
export interface CivitaiImageMeta {
  prompt?: string;
  negativePrompt?: string;
  steps?: number;
  cfgScale?: number;
  sampler?: string;
  scheduler?: string;
  seed?: number;
  clipSkip?: number;
  Model?: string;
  Size?: string;
  [key: string]: unknown;
}

export interface CivitaiImage {
  id: number;
  url: string;
  width: number;
  height: number;
  type?: string;
  nsfwLevel?: string;
  baseModel?: string;
  username?: string;
  postId?: number;
  createdAt?: string;
  stats?: Record<string, number>;
  meta?: CivitaiImageMeta | null;
  /** Added by our backend, not by CivitAI. */
  recreatable: Recreatable;
}

export interface ImageSearchMetadata {
  nextCursor?: string;
  nextPage?: string;
}

export interface ImageSearchResult {
  items: CivitaiImage[];
  metadata: ImageSearchMetadata;
}

/**
 * `/api/v1/images` has no free-text query — a `query` parameter is silently ignored —
 * so searching is filter-driven only.
 */
export interface ImageSearchParams {
  sort?: string;
  period?: string;
  nsfw?: string;
  baseModel?: string;
  type?: string;
  username?: string;
  modelId?: string;
  cursor?: string;
  limit?: number;
}

/** A model the recreated workflow refers to, matched against the local library. */
export interface ImageResource {
  kind: string;
  name: string;
  weight: number;
  hash: string;
  model_version_id: string;
  status: 'installed' | 'missing' | 'unresolvable';
  filename?: string;
  download_url?: string;
  size_kb?: number;
  model_type?: string;
  base_model?: string;
}

export interface RecreateResult {
  entry_id: number;
  workflow: StoredWorkflow;
  source: Recreatable;
  base_model: string;
  /** True when the SD-shaped template will not run as-is for this base model. */
  template_warning: boolean;
  resources: ImageResource[];
}

const API = '/tiny-model-manager/api';

@Injectable({ providedIn: 'root' })
export class ImageService {
  private readonly http = inject(HttpClient);

  search(opts: ImageSearchParams = {}): Observable<ImageSearchResult> {
    const params: Record<string, string | number> = {};
    if (opts.sort) {
      params['sort'] = opts.sort;
      if (opts.period) params['period'] = opts.period;
    }
    if (opts.nsfw) params['nsfw'] = opts.nsfw;
    if (opts.baseModel) params['base_model'] = opts.baseModel;
    if (opts.type) params['type'] = opts.type;
    if (opts.username) params['username'] = opts.username;
    if (opts.modelId) params['model_id'] = opts.modelId;
    if (opts.cursor) params['cursor'] = opts.cursor;
    if (opts.limit) params['limit'] = opts.limit;
    return this.http
      .get<{ success: boolean; data: ImageSearchResult }>(`${API}/images/search`, { params })
      .pipe(
        map((r) => ({
          items: r.data.items ?? [],
          metadata: r.data.metadata ?? {},
        })),
      );
  }

  get(imageId: number): Observable<CivitaiImage> {
    return this.http
      .get<{ success: boolean; data: CivitaiImage }>(`${API}/images/${imageId}`)
      .pipe(map((r) => r.data));
  }

  recreate(imageId: number): Observable<RecreateResult> {
    return this.http
      .post<{ success: boolean; data: RecreateResult }>(`${API}/images/${imageId}/recreate`, {})
      .pipe(map((r) => ({ ...r.data, resources: r.data.resources ?? [] })));
  }

  resolveResources(imageId: number): Observable<ImageResource[]> {
    return this.http
      .post<{ success: boolean; data: { resources: ImageResource[] } }>(
        `${API}/images/resolve-resources`,
        { image_id: String(imageId) },
      )
      .pipe(map((r) => r.data.resources ?? []));
  }
}
