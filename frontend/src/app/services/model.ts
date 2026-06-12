import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

export interface ModelFile {
  filename: string;
  base_dir: string;
  size_bytes: number;
  modified_at: number;
  metadata?: ModelMeta;
}

export interface ModelMeta {
  description: string;
  trigger_words: string[];
  tags: string[];
  media: MediaItem[];
  base_model: string;
  source_platform: string;
  source_url: string;
  size_bytes: number;
  created_at?: string;
  readme_html?: string;
  civitai_version_name?: string;
}

export interface MediaItem {
  id: number;
  media_type: string;
  local_path: string;
}

/** Result of a metadata re-fetch: either fresh metadata, or a signal that the stale
 *  record was pruned because the file no longer exists on disk. */
export type RefetchResult = { removed: true } | { removed: false; meta: ModelMeta };

export interface RefetchPreviewOld {
  description: string;
  trigger_words: string[];
  tags: string[];
  base_model: string;
  media: MediaItem[];
  last_edited_at: {
    description: string | null;
    trigger_words: string | null;
    tags: string | null;
    base_model: string | null;
  };
}

export interface RefetchPreviewNew {
  description: string;
  trigger_words: string[];
  tags: string[];
  base_model: string;
  media_urls: string[];
}

export interface RefetchPreviewResponse {
  old: RefetchPreviewOld;
  new: RefetchPreviewNew;
  expires_at: string;
  no_changes: boolean;
  removed?: boolean;
}

export interface RefetchApplyRequest {
  description: string;
  trigger_words: string[];
  tags: string[];
  base_model: string;
  replace_media: boolean;
  media_urls: string[];
  keep_existing_media: string[];
}

export interface RepoFile {
  filename: string;
  model_type: string;
  size_bytes: number | null;
  download_url: string;
  source_page_url: string;
  is_downloaded: boolean;
  added_at: number | null;
  installed_path: string;
  base_model: string;
}

export interface InstalledFile {
  filename: string;
  model_type: string;
  size_bytes: number;
  modified_at: number;
  civitai_version_name?: string;
}

export interface CatalogEntry {
  id: number;
  source_platform: string;
  source_page_id: string;
  source_page_url: string;
  display_name: string;
  thumbnail_url: string;
  base_model: string;
  created_at: string;
  model_type: string;
  is_empty: boolean;
  installed_files: InstalledFile[];
  trigger_words?: string[];
}

export interface CatalogEntryDetail extends CatalogEntry {
  repo_files: RepoFile[];
  // Catalog-owned source-page metadata (present even when no file is installed).
  description: string;
  trigger_words: string[];
  tags: string[];
  media: MediaItem[];
  readme_html?: string;
}

export interface CatalogListResponse {
  entries: CatalogEntry[];
  unknown_files: Record<string, ModelFile[]>;
}

const API = '/tiny-model-manager/api';

@Injectable({ providedIn: 'root' })
export class ModelService {
  constructor(private readonly http: HttpClient) {}

  listModels(): Observable<Record<string, ModelFile[]>> {
    return this.http
      .get<{ success: boolean; data: Record<string, ModelFile[]> }>(`${API}/models`)
      .pipe(map((r) => r.data));
  }

  deleteModel(modelType: string, path: string): Observable<void> {
    return this.http.delete<void>(`${API}/models/${modelType}/${path}`);
  }

  getMetadata(modelType: string, path: string): Observable<ModelMeta> {
    return this.http
      .get<{ success: boolean; data: ModelMeta }>(`${API}/models/${modelType}/${path}/metadata`)
      .pipe(map((r) => r.data));
  }

  updateMetadata(modelType: string, path: string, meta: Partial<ModelMeta>): Observable<void> {
    return this.http.put<void>(`${API}/models/${modelType}/${path}/metadata`, meta);
  }

  updateMetadataWithPath(
    modelType: string,
    path: string,
    meta: Partial<ModelMeta>,
  ): Observable<{ new_path: string }> {
    return this.http
      .put<{
        success: boolean;
        new_path: string;
      }>(`${API}/models/${modelType}/${path}/metadata`, meta)
      .pipe(map((r) => ({ new_path: r.new_path ?? path })));
  }

  refetchMetadata(modelType: string, path: string): Observable<RefetchResult> {
    return this.http
      .post<{
        success: boolean;
        data: (ModelMeta & { removed?: boolean }) | { removed: true };
      }>(`${API}/models/${modelType}/${path}/refetch`, {})
      .pipe(
        map((r) => {
          // When the file no longer exists on disk the backend prunes the stale record
          // and returns { removed: true } instead of metadata.
          if ('removed' in r.data && r.data.removed) return { removed: true as const };
          return { removed: false as const, meta: r.data as ModelMeta };
        }),
      );
  }

  getModelTypes(): Observable<string[]> {
    return this.http
      .get<{ success: boolean; data: string[] }>(`${API}/model-types`)
      .pipe(map((r) => r.data));
  }

  moveModel(modelType: string, path: string, newType: string): Observable<void> {
    return this.http.post<void>(`${API}/models/${modelType}/${path}/move`, { new_type: newType });
  }

  getPendingQueue(): Observable<string[]> {
    return this.http
      .get<{ success: boolean; data: string[] }>(`${API}/reorganize/pending`)
      .pipe(map((r) => r.data));
  }

  getRepoFiles(modelType: string, path: string): Observable<RepoFile[]> {
    return this.http
      .get<{ success: boolean; data: RepoFile[] }>(`${API}/models/${modelType}/${path}/repo-files`)
      .pipe(map((r) => r.data));
  }

  listCatalog(): Observable<CatalogListResponse> {
    return this.http
      .get<{ success: boolean; data: CatalogListResponse }>(`${API}/catalog`)
      .pipe(map((r) => r.data));
  }

  getCatalogEntry(platform: string, pageId: string): Observable<CatalogEntryDetail> {
    return this.http
      .get<{ success: boolean; data: CatalogEntryDetail }>(`${API}/catalog/${platform}/${pageId}`)
      .pipe(map((r) => r.data));
  }

  removeCatalogEntry(platform: string, pageId: string): Observable<void> {
    return this.http.delete<void>(`${API}/catalog/${platform}/${pageId}`);
  }

  refetchCatalog(platform: string, pageId: string): Observable<CatalogEntryDetail> {
    return this.http
      .post<{
        success: boolean;
        data: CatalogEntryDetail;
      }>(`${API}/catalog/${platform}/${pageId}/refetch`, {})
      .pipe(map((r) => r.data));
  }

  updateCatalogMetadata(
    platform: string,
    pageId: string,
    meta: { description?: string; trigger_words?: string[]; tags?: string[]; base_model?: string },
  ): Observable<void> {
    return this.http.put<void>(`${API}/catalog/${platform}/${pageId}/metadata`, meta);
  }

  linkSource(modelType: string, path: string, sourceUrl: string): Observable<void> {
    return this.http.post<void>(`${API}/models/${modelType}/${path}/link-source`, {
      source_url: sourceUrl,
    });
  }

  organizeIntoSubfolders(): Observable<{ moved: number; skipped: number; errors: number }> {
    return this.http
      .post<{
        success: boolean;
        data: { moved: number; skipped: number; errors: number };
      }>(`${API}/models/organize`, {})
      .pipe(map((r) => r.data));
  }

  refetchPreview(modelType: string, path: string): Observable<RefetchPreviewResponse> {
    return this.http
      .post<{
        success: boolean;
        data: RefetchPreviewResponse;
      }>(`${API}/models/${modelType}/${path}/refetch-preview`, {})
      .pipe(map((r) => r.data));
  }

  refetchApply(
    modelType: string,
    path: string,
    body: RefetchApplyRequest,
  ): Observable<RefetchResult> {
    return this.http
      .post<{
        success: boolean;
        data: (ModelMeta & { removed?: boolean }) | { removed: true };
      }>(`${API}/models/${modelType}/${path}/refetch-apply`, body)
      .pipe(
        map((r) => {
          if ('removed' in r.data && r.data.removed) return { removed: true as const };
          return { removed: false as const, meta: r.data as ModelMeta };
        }),
      );
  }
}
