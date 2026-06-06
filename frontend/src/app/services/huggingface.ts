import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

export interface HfModel {
  id: string;
  modelId: string;
  downloads: number;
  tags: string[];
  thumbnail?: string;
  formats?: string[];
  images?: string[];
  description?: string;
}

export interface HfSearchResult {
  items: HfModel[];
  hasMore: boolean;
  nextPage: number;
}

const API = '/tiny-model-manager/api';

@Injectable({ providedIn: 'root' })
export class HuggingFaceService {
  constructor(private readonly http: HttpClient) {}

  search(
    q: string,
    type = '',
    p = 0,
    sort = 'downloads',
    direction = -1,
    format = '',
    tags: string[] = [],
  ): Observable<HfSearchResult> {
    const params: Record<string, string | number> = { q, type, p, sort, direction, format };
    if (tags.length) params['tags'] = tags.join(',');
    return this.http
      .get<{
        success: boolean;
        data: HfSearchResult;
      }>(`${API}/search/huggingface`, { params })
      .pipe(map((r) => r.data));
  }

  getFiles(repo: string): Observable<{ filename: string; size: number; url: string }[]> {
    return this.http
      .get<{
        success: boolean;
        data: { filename: string; size: number; url: string }[];
      }>(`${API}/search/huggingface/files`, { params: { repo } })
      .pipe(map((r) => r.data));
  }

  getReadme(repo: string): Observable<string> {
    return this.http
      .get<{
        success: boolean;
        data: { description: string };
      }>(`${API}/huggingface/readme`, { params: { repo } })
      .pipe(map((r) => r.data.description));
  }

  resolveDirectLink(repo: string): Observable<{ image_urls: string[] }> {
    return this.http
      .get<{
        success: boolean;
        data: { image_urls: string[] };
      }>(`${API}/huggingface/resolve`, { params: { repo } })
      .pipe(map((r) => r.data));
  }
}
