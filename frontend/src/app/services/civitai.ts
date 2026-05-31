import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

export interface CivitaiFile {
  id: number;
  name: string;
  type: string;
  sizeKB: number;
  downloadUrl: string;
  primary: boolean;
  metadata: { format: string; size: string; fp: string };
}

export interface CivitaiVersion {
  id: number;
  name: string;
  baseModel: string;
  downloadUrl: string;
  trainedWords: string[];
  files: CivitaiFile[];
  images: { url: string; type?: string }[];
}

export interface CivitaiModel {
  id: number;
  name: string;
  type: string;
  description: string;
  tags?: string[];
  modelVersions: CivitaiVersion[];
  creator: { username: string };
  stats: { downloadCount: number; thumbsUpCount: number; thumbsDownCount: number };
}

export interface CivitaiDirectLinkInfo {
  filename: string;
  model_type: string;
  size_kb: number;
  image_urls: string[];
}

export interface CivitaiSearchMetadata {
  nextCursor?: string;
  nextPage?: number;
  totalItems?: number;
  totalPages?: number;
}

export interface CivitaiVersionsResult {
  versions: CivitaiVersion[];
  model_type: string;
}

const API = '/tiny-model-manager/api';

@Injectable({ providedIn: 'root' })
export class CivitaiService {
  constructor(private http: HttpClient) {}

  search(
    q: string,
    type = '',
    page = 1,
    cursor = '',
    baseModel = '',
    sort = '',
    period = '',
    tags: string[] = [],
  ): Observable<{ items: CivitaiModel[]; metadata: CivitaiSearchMetadata }> {
    const params: Record<string, string | number> = { q, type };
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
      .get<{
        success: boolean;
        data: { items: CivitaiModel[]; metadata: CivitaiSearchMetadata };
      }>(`${API}/search/civitai`, { params })
      .pipe(map((r) => ({ items: r.data.items ?? [], metadata: r.data.metadata ?? {} })));
  }

  getVersions(modelId: number): Observable<CivitaiVersionsResult> {
    return this.http
      .get<{ success: boolean; data: CivitaiVersionsResult }>(`${API}/civitai/versions/${modelId}`)
      .pipe(map((r) => r.data));
  }

  resolveDirectLink(versionId: number): Observable<CivitaiDirectLinkInfo> {
    return this.http
      .get<{ success: boolean; data: CivitaiDirectLinkInfo }>(`${API}/civitai/resolve/${versionId}`)
      .pipe(map((r) => r.data));
  }
}
