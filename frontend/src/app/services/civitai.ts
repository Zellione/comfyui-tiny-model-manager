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
  images: { url: string }[];
}

export interface CivitaiModel {
  id: number;
  name: string;
  type: string;
  description: string;
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

const API = '/tiny-model-manager/api';

@Injectable({ providedIn: 'root' })
export class CivitaiService {
  constructor(private http: HttpClient) {}

  search(q: string, type = '', page = 1, cursor = ''): Observable<{ items: CivitaiModel[]; metadata: any }> {
    const params: Record<string, string | number> = { q, type };
    if (q && cursor) {
      params['cursor'] = cursor;
    } else {
      params['page'] = page;
    }
    return this.http
      .get<{ success: boolean; data: any }>(`${API}/search/civitai`, { params })
      .pipe(map(r => ({ items: r.data.items ?? [], metadata: r.data.metadata ?? {} })));
  }

  getVersions(modelId: number): Observable<CivitaiVersion[]> {
    return this.http
      .get<{ success: boolean; data: CivitaiVersion[] }>(`${API}/civitai/versions/${modelId}`)
      .pipe(map(r => r.data));
  }

  resolveDirectLink(versionId: number): Observable<CivitaiDirectLinkInfo> {
    return this.http
      .get<{ success: boolean; data: CivitaiDirectLinkInfo }>(`${API}/civitai/resolve/${versionId}`)
      .pipe(map(r => r.data));
  }
}
