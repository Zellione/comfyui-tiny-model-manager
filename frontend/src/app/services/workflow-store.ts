import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { CivitaiModel, CivitaiSearchMetadata } from './civitai';
import { MediaItem } from './model';

/**
 * The stored-workflow API (F-129).
 *
 * Distinct from `services/workflow.ts`, which queues loader-node insertion into the open
 * ComfyUI graph. This one owns the workflow *store*: browsing CivitAI's Workflows type,
 * downloading the graphs an entry ships, and exporting or loading a stored graph.
 */

/** One ComfyUI graph extracted from a downloaded archive. */
export interface StoredWorkflow {
  id: number;
  entry_id: number;
  name: string;
  local_path: string;
  version_id: string;
  version_name: string;
  node_count: number;
  created_at?: string;
}

/** A downloaded CivitAI workflow page; owns the metadata and media its graphs share. */
export interface WorkflowEntry {
  id: number;
  source_platform: string;
  source_page_id: string;
  source_page_url: string;
  display_name: string;
  description: string;
  base_model: string;
  tags: string[];
  thumbnail_url: string;
  media_hash: string;
  created_at?: string;
  items: StoredWorkflow[];
  media: MediaItem[];
}

export interface WorkflowSearchResult {
  items: CivitaiModel[];
  metadata: CivitaiSearchMetadata;
  /** Version ids that already have at least one stored graph. */
  installed_version_ids: string[];
}

export interface WorkflowSearchParams {
  q: string;
  cursor?: string;
  page?: number;
  baseModel?: string;
  sort?: string;
  period?: string;
  tags?: string[];
}

export interface WorkflowDownloadResult {
  entry_id: number;
  workflows: StoredWorkflow[];
}

const API = '/tiny-model-manager/api';

@Injectable({ providedIn: 'root' })
export class WorkflowStoreService {
  private readonly http = inject(HttpClient);

  search(opts: WorkflowSearchParams): Observable<WorkflowSearchResult> {
    const { q, cursor = '', page = 1, baseModel = '', sort = '', period = '', tags = [] } = opts;
    const params: Record<string, string | number> = { q };
    if (cursor) {
      params['cursor'] = cursor;
    } else {
      params['page'] = page;
    }
    if (baseModel) params['base_model'] = baseModel;
    if (sort) {
      params['sort'] = sort;
      if (period) params['period'] = period;
    }
    if (tags.length) params['tags'] = tags.join(',');
    return this.http
      .get<{ success: boolean; data: WorkflowSearchResult }>(`${API}/workflows/search`, { params })
      .pipe(
        map((r) => ({
          items: r.data.items ?? [],
          metadata: r.data.metadata ?? {},
          installed_version_ids: r.data.installed_version_ids ?? [],
        })),
      );
  }

  download(modelId: number, versionId: number): Observable<WorkflowDownloadResult> {
    return this.http
      .post<{
        success: boolean;
        data: WorkflowDownloadResult;
      }>(`${API}/workflows/download`, { model_id: String(modelId), version_id: String(versionId) })
      .pipe(map((r) => r.data));
  }

  list(): Observable<WorkflowEntry[]> {
    return this.http
      .get<{ success: boolean; data: WorkflowEntry[] }>(`${API}/workflows`)
      .pipe(map((r) => r.data ?? []));
  }

  deleteEntry(entryId: number): Observable<void> {
    return this.http.delete<void>(`${API}/workflows/${entryId}`);
  }

  /** Copy a stored graph into ComfyUI's own workflow browser directory. */
  exportWorkflow(workflowId: number): Observable<{ path: string }> {
    return this.http
      .post<{
        success: boolean;
        data: { path: string };
      }>(`${API}/workflows/${workflowId}/export`, {})
      .pipe(map((r) => r.data));
  }

  /** Queue a graph for the ComfyUI extension to load onto the open canvas. */
  openInComfy(workflowId: number): Observable<{ id: string }> {
    return this.http
      .post<{ success: boolean; data: { id: string } }>(`${API}/workflows/${workflowId}/open`, {})
      .pipe(map((r) => r.data));
  }

  /** Direct URL to the raw graph JSON — used for the browser download action. */
  fileUrl(workflowId: number): string {
    return `${API}/workflows/${workflowId}/file`;
  }
}
