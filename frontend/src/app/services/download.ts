import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, interval, switchMap, startWith, shareReplay } from 'rxjs';
import { map } from 'rxjs/operators';

export interface DownloadTask {
  id: string;
  url: string;
  model_type: string;
  filename: string;
  platform: string;
  source_id: string;
  status: 'queued' | 'downloading' | 'done' | 'error';
  progress: number;
  downloaded_bytes: number;
  total_bytes: number;
  error: string | null;
}

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

export interface HfModel {
  id: string;
  modelId: string;
  downloads: number;
  tags: string[];
  thumbnail?: string;
}

export interface HfSearchResult {
  items: HfModel[];
  hasMore: boolean;
  nextPage: number;
}

const API = '/tiny-model-manager/api';

@Injectable({ providedIn: 'root' })
export class DownloadService {
  readonly activeTasks$: Observable<DownloadTask[]>;

  constructor(private http: HttpClient) {
    this.activeTasks$ = interval(2000).pipe(
      startWith(0),
      switchMap(() =>
        this.http
          .get<{ success: boolean; data: DownloadTask[] }>(`${API}/download/status`)
          .pipe(map(r => r.data))
      ),
      shareReplay(1)
    );
  }

  searchCivitai(q: string, type = '', page = 1, cursor = ''): Observable<{ items: CivitaiModel[]; metadata: any }> {
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

  searchHuggingFace(q: string, type = '', p = 0): Observable<HfSearchResult> {
    return this.http
      .get<{ success: boolean; data: HfSearchResult }>(`${API}/search/huggingface`, { params: { q, type, p } })
      .pipe(map(r => r.data));
  }

  getHfFiles(repo: string): Observable<{ filename: string; size: number; url: string }[]> {
    return this.http
      .get<{ success: boolean; data: any[] }>(`${API}/search/huggingface/files`, { params: { repo } })
      .pipe(map(r => r.data));
  }

  getCivitaiVersions(modelId: number): Observable<CivitaiVersion[]> {
    return this.http
      .get<{ success: boolean; data: CivitaiVersion[] }>(`${API}/civitai/versions/${modelId}`)
      .pipe(map(r => r.data));
  }

  startDownload(url: string, model_type: string, filename: string, platform: string, source_id = ''): Observable<{ task_id: string }> {
    return this.http
      .post<{ success: boolean; data: { task_id: string } }>(`${API}/download`, { url, model_type, filename, platform, source_id })
      .pipe(map(r => r.data));
  }
}
