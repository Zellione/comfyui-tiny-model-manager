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
  constructor(private http: HttpClient) {}

  search(q: string, type = '', p = 0, sort = 'downloads', direction = -1, format = ''): Observable<HfSearchResult> {
    return this.http
      .get<{ success: boolean; data: HfSearchResult }>(`${API}/search/huggingface`, { params: { q, type, p, sort, direction, format } })
      .pipe(map(r => r.data));
  }

  getFiles(repo: string): Observable<{ filename: string; size: number; url: string }[]> {
    return this.http
      .get<{ success: boolean; data: any[] }>(`${API}/search/huggingface/files`, { params: { repo } })
      .pipe(map(r => r.data));
  }

  resolveDirectLink(repo: string): Observable<{ image_urls: string[] }> {
    return this.http
      .get<{ success: boolean; data: { image_urls: string[] } }>(`${API}/huggingface/resolve`, { params: { repo } })
      .pipe(map(r => r.data));
  }
}
